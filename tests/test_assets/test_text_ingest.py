"""P0-1 unit tests: text ingestion + upload store."""
from __future__ import annotations

import os

import pytest

from vn_agent.assets import text_ingest, upload_store


class TestCJKDetection:
    def test_pure_english_is_not_cjk(self):
        assert not text_ingest.detect_cjk_dominant(
            "A quiet village where the last dragon slept."
        )

    def test_pure_chinese_is_cjk(self):
        assert text_ingest.detect_cjk_dominant(
            "宁静的村庄，最后一条龙沉睡在山谷之间，等待着某个未定的黄昏。"
        )

    def test_mostly_chinese_with_english_names_still_cjk(self):
        # Creator notes often mix English character IDs with Chinese narration.
        text = (
            "角色 Alice 是这个故事的主角。她住在小镇 Rivertown，"
            "与朋友 Bob 一起冒险。地图上标注了三个关键地点。"
        )
        assert text_ingest.detect_cjk_dominant(text)

    def test_empty_string_is_not_cjk(self):
        assert not text_ingest.detect_cjk_dominant("")

    def test_whitespace_only_is_not_cjk(self):
        assert not text_ingest.detect_cjk_dominant("   \n\n  ")


class TestChunker:
    def test_empty_returns_empty(self):
        assert text_ingest.chunk_text("", "notes.md") == []
        assert text_ingest.chunk_text("   \n  ", "notes.md") == []

    def test_short_english_returns_one_chunk(self):
        text = "A quiet village where the last dragon slept."
        chunks = text_ingest.chunk_text(text, "world.md")
        assert len(chunks) == 1
        assert chunks[0].text.strip() == text
        assert chunks[0].scope == "user_upload"
        # Provenance is populated by default.
        assert chunks[0].source_meta["source"] == "upload"
        assert chunks[0].source_meta["filename"] == "world.md"
        assert chunks[0].source_meta["license"] == "user_owned"
        assert chunks[0].source_meta["chunk_idx"] == 0
        assert chunks[0].source_meta["cjk_dominant"] is False

    def test_short_chinese_returns_one_chunk_marked_cjk(self):
        text = "宁静的村庄，最后一条龙沉睡在山谷之间，等待着某个未定的黄昏。"
        chunks = text_ingest.chunk_text(text, "世界观.md")
        assert len(chunks) == 1
        assert chunks[0].source_meta["cjk_dominant"] is True

    def test_long_english_splits_into_multiple_chunks(self):
        # Deliberately > _ENG_CHUNK_SIZE (800) — a mini fake creator brief.
        paragraph = "This is a foundational paragraph explaining the story world in detail. "
        text = "\n\n".join(paragraph * 12 for _ in range(4))
        chunks = text_ingest.chunk_text(text, "brief.md")
        assert len(chunks) >= 2
        # All chunks carry sequential indices.
        indices = [c.source_meta["chunk_idx"] for c in chunks]
        assert indices == list(range(len(chunks)))
        # Every chunk has the same filename provenance.
        assert all(c.source_meta["filename"] == "brief.md" for c in chunks)

    def test_long_chinese_splits_at_cjk_boundaries(self):
        # ~600 CJK chars — > _CJK_CHUNK_SIZE (300), so must split ≥ 2 chunks.
        sentence = "在这个古老的王国里，年轻的公主和她的守护者踏上了寻找失落神器的漫长旅程。"
        text = "\n\n".join(sentence * 5 for _ in range(3))
        chunks = text_ingest.chunk_text(text, "背景设定.md")
        assert len(chunks) >= 2
        assert all(c.source_meta["cjk_dominant"] is True for c in chunks)

    def test_web_search_source_carries_url_and_query(self):
        chunks = text_ingest.chunk_text(
            "Some fetched article body.",
            "en.wikipedia.org-Dragon.html",
            source="web_search",
            license="CC-BY",
            source_url="https://en.wikipedia.org/wiki/Dragon",
            search_query="dragon lore fantasy",
        )
        assert len(chunks) == 1
        meta = chunks[0].source_meta
        assert meta["source"] == "web_search"
        assert meta["license"] == "CC-BY"
        assert meta["source_url"] == "https://en.wikipedia.org/wiki/Dragon"
        assert meta["search_query"] == "dragon lore fantasy"


class TestExtractText:
    def test_markdown_bytes_decoded_utf8(self):
        text = "# 标题\n\n段落内容。"
        assert text_ingest.extract_text_from_bytes(text.encode("utf-8"), "note.md") == text

    def test_unknown_extension_falls_back_to_utf8(self):
        text = "raw content"
        assert text_ingest.extract_text_from_bytes(text.encode("utf-8"), "note.rando") == text

    def test_invalid_utf8_uses_replace(self):
        # Bytes with invalid utf-8 should not blow up — replace char is fine
        # for M0 (we lose some fidelity but never crash the endpoint).
        data = b"valid text \xff\xfe more"
        out = text_ingest.extract_text_from_bytes(data, "note.txt")
        assert "valid text" in out
        assert "more" in out


class TestUploadStore:
    @pytest.fixture(autouse=True)
    def _isolated_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv(upload_store._DATA_UPLOAD_ROOT_ENV, str(tmp_path))
        yield

    def test_save_and_load_roundtrip(self):
        job_id = "job-alpha"
        chunks = text_ingest.chunk_text("Hello world.", "greet.md")
        path = upload_store.save_chunks(job_id, chunks)
        assert path.exists()

        loaded = upload_store.load_chunks(job_id)
        assert len(loaded) == 1
        assert loaded[0].text.strip() == "Hello world."
        assert loaded[0].scope == "user_upload"
        assert loaded[0].source_meta["filename"] == "greet.md"

    def test_empty_chunks_no_file_write(self):
        job_id = "empty-job"
        path = upload_store.save_chunks(job_id, [])
        # Path is returned but should not exist (no chunks to persist).
        assert not path.exists()

    def test_multiple_uploads_accumulate(self):
        job_id = "job-beta"
        upload_store.save_chunks(job_id, text_ingest.chunk_text("First note.", "a.md"))
        upload_store.save_chunks(job_id, text_ingest.chunk_text("Second note.", "b.md"))
        loaded = upload_store.load_chunks(job_id)
        assert len(loaded) == 2
        assert {c.source_meta["filename"] for c in loaded} == {"a.md", "b.md"}

    def test_summarize_by_source_and_license(self):
        job_id = "job-summ"
        upload_store.save_chunks(job_id, text_ingest.chunk_text(
            "User note.", "world.md", source="upload", license="user_owned",
        ))
        upload_store.save_chunks(job_id, text_ingest.chunk_text(
            "Web article.", "wiki.html",
            source="web_search", license="CC-BY", source_url="https://x/y",
        ))
        summary = upload_store.summarize(job_id)
        assert summary["chunks"] == 2
        assert summary["by_source"] == {"upload": 1, "web_search": 1}
        assert summary["by_license"] == {"user_owned": 1, "CC-BY": 1}
        assert "world.md" in summary["files"]
        assert "https://x/y" in summary["files"]

    def test_summarize_empty_job(self):
        assert upload_store.summarize("nonexistent-job") == {
            "chunks": 0,
            "by_source": {},
            "by_license": {},
            "files": [],
        }

    def test_raw_persistence_best_effort(self):
        job_id = "job-raw"
        path = upload_store.save_raw(job_id, "notes.md", b"# markdown body")
        assert path is not None
        assert path.exists()
        assert path.read_bytes() == b"# markdown body"

    def test_raw_persistence_ignores_dangerous_extensions(self):
        # .exe should not survive — stem preserved, extension dropped.
        path = upload_store.save_raw("job-safe", "malware.exe", b"MZ...")
        assert path is not None
        # No extension — bytes are still written under sanitized name.
        assert path.suffix == ""

    def test_bad_job_id_rejected(self):
        with pytest.raises(ValueError):
            upload_store.save_chunks("../../etc/passwd", [])


class TestLoreIntegration:
    """Ensure build_lore_index accepts user_upload chunks without breaking."""

    @pytest.fixture(autouse=True)
    def _isolated_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv(upload_store._DATA_UPLOAD_ROOT_ENV, str(tmp_path))
        yield

    def test_index_accepts_user_upload_entities(self):
        try:
            import sentence_transformers  # noqa: F401
            import faiss  # noqa: F401
        except ImportError:
            pytest.skip("sentence-transformers / faiss not installed (assets extra)")

        from vn_agent.eval.lore import build_lore_index
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        script = VNScript(
            title="Test",
            theme="校园恋爱",
            description="一个关于友谊的故事。",
            start_scene_id="s1",
            scenes=[
                Scene(
                    id="s1",
                    title="开场",
                    description="开场场景",
                    background_id="school",
                    characters_present=["alice"],
                ),
            ],
        )
        characters = {
            "alice": CharacterProfile(
                id="alice",
                name="Alice",
                role="protagonist",
                personality="curious",
                background="Grew up in a small town.",
            ),
        }

        chunks = text_ingest.chunk_text(
            "背景设定：故事发生在江南水乡的一所高中。",
            "背景.md",
        )
        idx = build_lore_index(script, characters, user_upload_entities=chunks)
        if idx is None:
            pytest.skip("Lore index unavailable in this env")
        # user_upload entities exposed for downstream provenance readers.
        assert hasattr(idx, "user_upload_entities")
        assert len(idx.user_upload_entities) == 1
        assert idx.user_upload_entities[0].scope == "user_upload"
