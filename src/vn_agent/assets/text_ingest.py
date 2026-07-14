"""Text ingestion: uploaded md/pdf/docx → AnnotatedSession[user_upload] chunks.

Design decisions:
- CJK-aware chunking. Chinese averages ~1.5-2× denser than English per
  visual line, so we detect CJK content and drop chunk_size from 800→300
  to keep the retrieval window comparable. Also add CJK-specific separators
  so the splitter cuts on 。！？ instead of forcing English-style periods.
- Provenance-first. Every chunk carries source_meta (source, filename,
  license, uploaded_at, chunk_idx) so downstream diversity index and
  license gate work off byte-level truth, not caller-declared metadata.
- Graceful degrade. If langchain-text-splitters is missing, we fall back
  to a naive paragraph splitter — good enough for M0 unit tests, bad enough
  that production pipelines will emit a warning to install [assets] extra.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)

# Chunk-size floors — deliberately below langchain defaults (800/200) because
# retrieval top-k treats each chunk as one unit; oversized chunks bury signal.
_ENG_CHUNK_SIZE = 800
_ENG_CHUNK_OVERLAP = 150
_CJK_CHUNK_SIZE = 300
_CJK_CHUNK_OVERLAP = 60

# CJK detection threshold — if >= 20% of non-whitespace chars are CJK, treat
# the whole document as CJK-dominant. Mixed English/Chinese docs (e.g.
# creator notes with English character names + Chinese narration) fall on
# the CJK side, which is the safe choice: CJK settings work on English text
# just fine, while English settings on Chinese text produce mid-word cuts.
_CJK_RATIO_THRESHOLD = 0.20


def _is_cjk_char(ch: str) -> bool:
    """True if `ch` is CJK (Chinese/Japanese/Korean) ideograph, kana, or hangul."""
    if not ch or ch.isspace():
        return False
    code = ord(ch)
    return (
        0x3040 <= code <= 0x30FF   # Hiragana + Katakana
        or 0x3400 <= code <= 0x4DBF  # CJK Extension A
        or 0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0xAC00 <= code <= 0xD7AF  # Hangul syllables
        or 0xF900 <= code <= 0xFAFF  # CJK Compatibility
    )


def detect_cjk_dominant(text: str) -> bool:
    """Heuristic: is this document CJK-dominant enough to warrant CJK chunking?"""
    if not text:
        return False
    non_ws = [c for c in text if not c.isspace()]
    if not non_ws:
        return False
    cjk_count = sum(1 for c in non_ws if _is_cjk_char(c))
    return (cjk_count / len(non_ws)) >= _CJK_RATIO_THRESHOLD


def _default_separators(cjk: bool) -> list[str]:
    """Separator list ordered by "prefer to split on this first".

    RecursiveCharacterTextSplitter tries separators in order and only falls
    back to the next when the current one can't make chunks fit under
    chunk_size. So put paragraph breaks first, sentence breaks in the
    middle, character-level last.
    """
    if cjk:
        return [
            "\n\n",   # paragraph
            "\n",     # line
            "。",     # Chinese period
            "！", "？",
            "；", "：",
            "，",
            ".", "!", "?", ";", ":", ",",   # ASCII fallback
            " ",
            "",       # last resort: character-level
        ]
    return [
        "\n\n",
        "\n",
        ". ",
        "! ", "? ",
        "; ",
        ", ",
        " ",
        "",
    ]


def _naive_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Paragraph-based fallback when langchain-text-splitters is missing.

    Splits on blank lines first, then hard-slices anything over chunk_size.
    Overlap is honored best-effort. Not as good as langchain's recursive
    splitter but keeps M0 tests + demos runnable without the [assets] extra.
    """
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 2 <= chunk_size:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            # If the single paragraph is oversized, hard-slice.
            if len(p) > chunk_size:
                for i in range(0, len(p), max(1, chunk_size - chunk_overlap)):
                    chunks.append(p[i : i + chunk_size])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _split_text(text: str, cjk: bool) -> list[str]:
    """Split `text` into chunks using langchain-text-splitters when available."""
    chunk_size = _CJK_CHUNK_SIZE if cjk else _ENG_CHUNK_SIZE
    chunk_overlap = _CJK_CHUNK_OVERLAP if cjk else _ENG_CHUNK_OVERLAP

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        logger.warning(
            "langchain-text-splitters not installed; falling back to naive "
            "chunker. Install `uv sync --extra assets` for better quality."
        )
        return _naive_split(text, chunk_size, chunk_overlap)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_default_separators(cjk),
        # keep_separator=True keeps the boundary punctuation attached to
        # the *preceding* chunk, which matters for CJK: "。" belongs to
        # the sentence it ends, not the one it starts.
        keep_separator=True,
        length_function=len,
    )
    return splitter.split_text(text)


def _normalize_upload_id(filename: str) -> str:
    """Turn a filename into a filesystem/id-safe upload_id.

    Keeps ASCII alphanumeric + underscore + hyphen; drops everything else
    (including CJK, which is intentional — we don't want CJK in filesystem
    paths on Windows because encoding surprises hurt everyone).
    """
    stem = re.sub(r"\.[^.]+$", "", filename or "upload")
    stem = unicodedata.normalize("NFKD", stem)
    stem = re.sub(r"[^\w\-.]", "_", stem, flags=re.ASCII)
    return stem[:64] or "upload"


def chunk_text(
    text: str,
    filename: str,
    *,
    source: str = "upload",
    license: str = "user_owned",
    source_url: str | None = None,
    search_query: str | None = None,
) -> list[AnnotatedSession]:
    """Split `text` into AnnotatedSession[user_upload] chunks with provenance.

    Args:
        text: raw document body (UTF-8).
        filename: original filename (for id + provenance display).
        source: "upload" | "web_search" | "local_library".
        license: SPDX-ish tag; unknown allowed but export gate will block it.
        source_url: original URL when source="web_search".
        search_query: original query when source="web_search".

    Returns [] when text is empty or all whitespace.
    """
    if not text or not text.strip():
        return []

    cjk = detect_cjk_dominant(text)
    upload_id = _normalize_upload_id(filename)
    now = datetime.now(timezone.utc).isoformat()
    raw_chunks = _split_text(text.strip(), cjk=cjk)

    sessions: list[AnnotatedSession] = []
    for idx, chunk in enumerate(raw_chunks):
        chunk = chunk.strip()
        if not chunk:
            continue
        meta = {
            "source": source,
            "filename": filename,
            "license": license,
            "uploaded_at": now,
            "chunk_idx": idx,
            "cjk_dominant": cjk,
        }
        if source_url:
            meta["source_url"] = source_url
        if search_query:
            meta["search_query"] = search_query
        sessions.append(
            AnnotatedSession(
                id=f"user_upload:{upload_id}:{idx}",
                title=f"{filename} #{idx + 1}",
                text=chunk,
                strategy=None,
                scope="user_upload",
                source_meta=meta,
            )
        )
    return sessions


def extract_text_from_bytes(data: bytes, filename: str) -> str:
    """Decode uploaded bytes → plain text.

    Supports .md / .txt (utf-8 decode), .pdf (pypdf), .docx (python-docx).
    Unknown extensions are attempted as utf-8 with error='replace'.
    Missing optional deps raise ImportError with an actionable message
    instead of a cryptic AttributeError.
    """
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()

    if ext in {"md", "txt", "markdown", ""}:
        return data.decode("utf-8", errors="replace")

    if ext == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "pypdf not installed — needed to ingest PDF uploads. "
                "Run `uv sync --extra assets`."
            ) from exc
        from io import BytesIO

        reader = PdfReader(BytesIO(data))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)

    if ext == "docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ImportError(
                "python-docx not installed — needed to ingest DOCX uploads. "
                "Run `uv sync --extra assets`."
            ) from exc
        from io import BytesIO

        doc = Document(BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs)

    return data.decode("utf-8", errors="replace")


def ingest_upload(
    data: bytes,
    filename: str,
    *,
    source: str = "upload",
    license: str = "user_owned",
    source_url: str | None = None,
    search_query: str | None = None,
) -> list[AnnotatedSession]:
    """End-to-end: bytes → text → chunks. Convenience for the upload endpoint."""
    text = extract_text_from_bytes(data, filename)
    return chunk_text(
        text,
        filename,
        source=source,
        license=license,
        source_url=source_url,
        search_query=search_query,
    )


# Type export for other assets modules that reason about chunk iterables.
Chunks = Iterable[AnnotatedSession]
