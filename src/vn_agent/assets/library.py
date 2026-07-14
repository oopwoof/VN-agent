"""Local open-source asset library — manifest-driven, semantic-tag retrieval.

Design decisions:
- Manifest-first, not scanner-first. A JSON manifest is the source of
  truth for what's available + its license + attribution. Scanning the
  filesystem would silently include files without license metadata, which
  breaks the export gate (P0-4) and defeats the purpose of a curated
  asset library.
- Retrieval is intentionally simple at M0: tag intersection + optional
  sentence-transformers cosine over a concatenated "tag document" per
  asset. No FAISS index — libraries are small (< 500 entries expected)
  and rebuild-per-query keeps deployment trivial.
- Zero deps required. sentence-transformers is optional; when unavailable
  we fall back to substring/tag intersection. Callers get a match or None.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_DEFAULT_MANIFEST_ENV = "VN_AGENT_ASSET_LIBRARY"
_DEFAULT_MANIFEST_PATH = Path("data") / "assets" / "opensource" / "manifest.json"

# Whitelist of licenses that pass the M0 export gate without prompting.
# The gate lives in license_gate.py (P0-4); this constant is duplicated
# here as a doc anchor for reviewers scanning library.py in isolation.
_ACCEPTED_LICENSES = frozenset({"CC0", "CC-BY", "CC-BY-SA"})

_VALID_TYPES = frozenset({"background", "character_sprite", "bgm", "sfx"})


@dataclass(frozen=True)
class LibraryAsset:
    """One entry from the manifest — a curated open-source asset with provenance."""
    id: str
    type: str
    path: Path                              # resolved absolute path
    license: str
    attribution: str
    tags: tuple[str, ...] = ()
    width: int | None = None
    height: int | None = None
    notes: str = ""
    # Kept as a plain dict for extension without schema bumps.
    extra: dict = field(default_factory=dict)

    def to_source_meta(self, query: str | None = None) -> dict:
        """Provenance payload for AnnotatedSession.source_meta / diversity index."""
        meta = {
            "source": "local_library",
            "asset_id": self.id,
            "asset_type": self.type,
            "license": self.license,
            "attribution": self.attribution,
            "path": str(self.path),
        }
        if query:
            meta["match_query"] = query
        return meta


class AssetLibrary:
    """Read-only view over a manifest.json describing local CC0/CC-BY assets."""

    def __init__(self, manifest_path: Path | None = None):
        self.manifest_path = manifest_path or _resolve_manifest_path()
        self._assets: list[LibraryAsset] = []
        self._loaded = False

    @property
    def size(self) -> int:
        self._ensure_loaded()
        return len(self._assets)

    def all(self) -> list[LibraryAsset]:
        self._ensure_loaded()
        return list(self._assets)

    def by_type(self, asset_type: str) -> list[LibraryAsset]:
        self._ensure_loaded()
        return [a for a in self._assets if a.type == asset_type]

    def find_match(
        self,
        query: str,
        asset_type: str,
        *,
        min_score: float = 0.35,
        top_k: int = 1,
    ) -> list[tuple[LibraryAsset, float]]:
        """Rank assets of the given type by relevance to `query`.

        Uses sentence-transformers cosine when available; falls back to
        substring + tag-intersection when the [rag] extra isn't installed.
        Returns [] when no candidate clears `min_score`.
        """
        self._ensure_loaded()
        pool = self.by_type(asset_type)
        if not pool or not query:
            return []

        scored = _score_pool(query, pool)
        scored.sort(key=lambda kv: kv[1], reverse=True)
        top = [(a, s) for a, s in scored if s >= min_score][:top_k]
        if not top:
            logger.debug(
                f"AssetLibrary: no {asset_type} matched query={query!r} "
                f"(best score {max((s for _, s in scored), default=0.0):.3f} < {min_score})"
            )
        return top

    def find_one(
        self,
        query: str,
        asset_type: str,
        *,
        min_score: float = 0.35,
    ) -> LibraryAsset | None:
        """Convenience: top-1 or None."""
        matches = self.find_match(query, asset_type, min_score=min_score, top_k=1)
        return matches[0][0] if matches else None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._assets = _load_manifest(self.manifest_path)
        self._loaded = True


# ----------------------------------------------------------------------
# Module-level helpers (kept separate so tests can exercise scoring in
# isolation without instantiating a full library).
# ----------------------------------------------------------------------


def _resolve_manifest_path() -> Path:
    override = os.environ.get(_DEFAULT_MANIFEST_ENV)
    if override:
        return Path(override)
    return _DEFAULT_MANIFEST_PATH


def _load_manifest(manifest_path: Path) -> list[LibraryAsset]:
    """Parse manifest.json into LibraryAsset[]. Missing file → empty."""
    if not manifest_path.exists():
        logger.info(f"AssetLibrary: manifest not found at {manifest_path} — empty library")
        return []

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning(f"AssetLibrary: manifest {manifest_path} is not valid JSON: {e}")
        return []

    raw = data.get("assets") or []
    manifest_dir = manifest_path.parent
    out: list[LibraryAsset] = []
    for entry in raw:
        try:
            asset = _entry_to_asset(entry, manifest_dir)
        except ValueError as e:
            logger.warning(f"AssetLibrary: skipping bad entry {entry!r}: {e}")
            continue
        out.append(asset)
    return out


def _entry_to_asset(entry: dict, manifest_dir: Path) -> LibraryAsset:
    """Validate + resolve one manifest entry. Raises ValueError on bad data."""
    required = ("id", "type", "path", "license", "attribution")
    missing = [k for k in required if not entry.get(k)]
    if missing:
        raise ValueError(f"missing required fields: {missing}")

    atype = str(entry["type"]).strip()
    if atype not in _VALID_TYPES:
        raise ValueError(f"invalid type {atype!r}, allowed: {sorted(_VALID_TYPES)}")

    raw_path = Path(entry["path"])
    resolved = raw_path if raw_path.is_absolute() else (manifest_dir / raw_path)
    # Manifest lies about the file existing → warn but don't hard-fail;
    # curators sometimes remove files before removing the entry.
    if not resolved.exists():
        logger.warning(
            f"AssetLibrary: manifest entry {entry['id']} points at missing "
            f"path {resolved}"
        )

    tags = tuple(str(t).strip().lower() for t in (entry.get("tags") or []) if str(t).strip())

    return LibraryAsset(
        id=str(entry["id"]),
        type=atype,
        path=resolved,
        license=str(entry["license"]).strip(),
        attribution=str(entry["attribution"]).strip(),
        tags=tags,
        width=entry.get("width"),
        height=entry.get("height"),
        notes=str(entry.get("notes") or ""),
        extra={k: v for k, v in entry.items() if k not in {
            "id", "type", "path", "license", "attribution",
            "tags", "width", "height", "notes",
        }},
    )


def _tokenize(text: str) -> list[str]:
    """Cheap lowercase tokenizer — good enough for tag/keyword overlap.

    Splits on whitespace and common punctuation. Kept ASCII-simple; CJK
    single-character tokens fall out naturally because we don't drop
    non-ASCII chars.
    """
    import re

    return [t for t in re.split(r"[\s,;/|]+", text.lower()) if t]


def _lexical_score(query: str, asset: LibraryAsset) -> float:
    """Tag intersection + substring bonus, normalized to [0, 1].

    Zero deps. Tuned so a single exact tag hit lands ~0.5 (above the
    default min_score=0.35) — that's what "match" feels like in practice.
    """
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 0.0

    tag_hits = sum(1 for t in asset.tags if t in q_tokens)
    tag_ratio = tag_hits / max(len(asset.tags), 1) if asset.tags else 0.0
    q_ratio = tag_hits / len(q_tokens)

    # Substring bonus — id/notes containing any query token gets a small nudge.
    haystack = f"{asset.id} {asset.notes}".lower()
    substring_hits = sum(1 for t in q_tokens if t in haystack) / len(q_tokens)

    # Weighted mix: tag intersection is primary, id/notes substring is a
    # tie-breaker for close matches. Ceiling at 1.0.
    score = 0.55 * tag_ratio + 0.30 * q_ratio + 0.15 * substring_hits
    return min(score, 1.0)


def _semantic_score(query: str, assets: Iterable[LibraryAsset]) -> dict[str, float] | None:
    """Optional sentence-transformers scoring. Returns None if unavailable."""
    try:
        from sentence_transformers import SentenceTransformer, util
    except ImportError:
        return None

    try:
        from vn_agent.config import get_settings
        model_name = get_settings().embedding_model
    except Exception:  # noqa: BLE001
        model_name = "all-MiniLM-L6-v2"

    docs = []
    ids = []
    for a in assets:
        doc = " ".join([a.id, *a.tags, a.notes]).strip()
        if not doc:
            continue
        docs.append(doc)
        ids.append(a.id)

    if not docs:
        return None

    try:
        model = SentenceTransformer(model_name)
        query_emb = model.encode([query], normalize_embeddings=True)
        doc_emb = model.encode(docs, normalize_embeddings=True)
        sims = util.cos_sim(query_emb, doc_emb)[0].tolist()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"AssetLibrary: semantic scoring failed, using lexical fallback: {e}")
        return None

    return {aid: float(s) for aid, s in zip(ids, sims)}


def record_library_hit(
    output_dir: Path | str,
    asset_type: str,
    target_id: str,
    hit: "LibraryAsset",
    query: str = "",
) -> Path | None:
    """Append a library hit record to `{output_dir}/library_hits.jsonl`.

    Persistence lives with the run's output_dir (not job's data/uploads/)
    because the diversity index (P0-6) walks output_dir when computing
    the final blackboard `metrics.diversity_index`. Best-effort: failure
    is logged but never blocks the pipeline.
    """
    import json

    dst = Path(output_dir) / "library_hits.jsonl"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "asset_type": asset_type,
                "target_id": target_id,
                "query": query,
                **hit.to_source_meta(query=query),
            }, ensure_ascii=False))
            f.write("\n")
        return dst
    except OSError as e:
        logger.debug(f"Failed to record library hit for {target_id}: {e}")
        return None


def try_library_hit(
    query: str,
    asset_type: str,
    target_path: Path | str,
    *,
    library_instance: AssetLibrary | None = None,
    min_score: float = 0.35,
) -> LibraryAsset | None:
    """Agent bridge: if the library has a matching asset, copy it into place.

    Used by character_designer / scene_artist / music_director before their
    LLM-driven generation kicks in. On hit: the library file is copied to
    `target_path` and the LibraryAsset is returned (caller records provenance
    via `.to_source_meta()` for the diversity index). On miss: returns None
    and the agent falls through to LLM generation.

    Copy semantics chosen over symlink because Windows symlink permission
    is fiddly (v3 CLAUDE learned this the hard way with HF cache warnings)
    and Ren'Py bundling wants real bytes.
    """
    import shutil

    lib = library_instance or AssetLibrary()
    asset = lib.find_one(query, asset_type, min_score=min_score)
    if asset is None:
        return None

    if not asset.path.exists():
        logger.warning(
            f"AssetLibrary: matched {asset.id} but source path missing at {asset.path}"
        )
        return None

    target = Path(target_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset.path, target)
    except OSError as e:
        logger.warning(f"AssetLibrary: copy of {asset.id} → {target} failed: {e}")
        return None

    logger.info(
        f"AssetLibrary HIT: {asset_type} query={query!r} → {asset.id} "
        f"({asset.license}, {asset.attribution})"
    )
    return asset


def _score_pool(query: str, pool: list[LibraryAsset]) -> list[tuple[LibraryAsset, float]]:
    """Blend semantic (when available) with lexical fallback.

    Weights: 0.7 semantic + 0.3 lexical when both present. Lexical-only
    when semantic is unavailable. Semantic-only when an asset has no tags
    (semantic still fires on id + notes).
    """
    semantic_scores = _semantic_score(query, pool)
    out: list[tuple[LibraryAsset, float]] = []
    for a in pool:
        lex = _lexical_score(query, a)
        if semantic_scores is not None and a.id in semantic_scores:
            score = 0.7 * semantic_scores[a.id] + 0.3 * lex
        else:
            score = lex
        out.append((a, score))
    return out
