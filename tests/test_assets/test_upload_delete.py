"""P0-upload-delete unit tests: delete-by-filename + clear_all + summary sync."""
from __future__ import annotations

import pytest

from vn_agent.assets import text_ingest, upload_store


@pytest.fixture(autouse=True)
def _iso_upload_root(tmp_path, monkeypatch):
    monkeypatch.setenv(upload_store._DATA_UPLOAD_ROOT_ENV, str(tmp_path))
    yield


class TestDeleteByFilename:
    def test_deletes_matching_chunks(self):
        upload_store.save_chunks("job-a", text_ingest.chunk_text("A note.", "a.md"))
        upload_store.save_chunks("job-a", text_ingest.chunk_text("B note.", "b.md"))
        assert len(upload_store.load_chunks("job-a")) == 2

        removed = upload_store.delete_by_filename("job-a", "a.md")
        assert removed == 1

        remaining = upload_store.load_chunks("job-a")
        assert len(remaining) == 1
        assert remaining[0].source_meta["filename"] == "b.md"

    def test_deletes_multi_chunk_file(self):
        # A long doc splits into >1 chunk; delete should nuke them all.
        long_body = "Paragraph.\n\n" * 200  # forces multi-chunk under any splitter
        upload_store.save_chunks("job-b", text_ingest.chunk_text(long_body, "big.md"))
        upload_store.save_chunks("job-b", text_ingest.chunk_text("Small.", "small.md"))
        before = len(upload_store.load_chunks("job-b"))
        assert before >= 2

        removed = upload_store.delete_by_filename("job-b", "big.md")
        assert removed >= 1  # at least the big file's chunks
        remaining = upload_store.load_chunks("job-b")
        assert all(c.source_meta["filename"] == "small.md" for c in remaining)

    def test_missing_filename_is_noop(self):
        upload_store.save_chunks("job-c", text_ingest.chunk_text("only file.", "only.md"))
        removed = upload_store.delete_by_filename("job-c", "nonexistent.md")
        assert removed == 0
        # Original chunks still present.
        assert len(upload_store.load_chunks("job-c")) == 1

    def test_delete_from_empty_job_is_noop(self):
        assert upload_store.delete_by_filename("job-empty", "anything.md") == 0

    def test_empty_filename_is_noop(self):
        upload_store.save_chunks("job-d", text_ingest.chunk_text("keep me.", "k.md"))
        assert upload_store.delete_by_filename("job-d", "") == 0
        assert len(upload_store.load_chunks("job-d")) == 1

    def test_unlinks_jsonl_when_last_file_deleted(self):
        upload_store.save_chunks("job-e", text_ingest.chunk_text("only.", "only.md"))
        path = upload_store.upload_dir("job-e") / "uploads.jsonl"
        assert path.exists()
        removed = upload_store.delete_by_filename("job-e", "only.md")
        assert removed == 1
        # jsonl removed → subsequent summarize is clean.
        assert not path.exists()
        assert upload_store.summarize("job-e") == {
            "chunks": 0, "by_source": {}, "by_license": {}, "files": [],
        }


class TestClearAll:
    def test_clears_chunks_and_raw(self):
        upload_store.save_chunks("job-f", text_ingest.chunk_text("A.", "a.md"))
        upload_store.save_chunks("job-f", text_ingest.chunk_text("B.", "b.md"))
        upload_store.save_raw("job-f", "a.md", b"raw bytes a")
        upload_store.save_raw("job-f", "b.md", b"raw bytes b")

        prior_count = len(upload_store.load_chunks("job-f"))
        removed = upload_store.clear_all("job-f")
        assert removed == prior_count

        # Store is empty afterward.
        assert upload_store.load_chunks("job-f") == []
        # raw/ directory is gone.
        raw_dir = upload_store.upload_dir("job-f") / "raw"
        assert not raw_dir.exists()

    def test_clear_on_empty_job_is_noop(self):
        assert upload_store.clear_all("job-none") == 0


class TestSummaryConsistency:
    def test_summary_reflects_deletion(self):
        upload_store.save_chunks("job-g", text_ingest.chunk_text(
            "A.", "a.md", license="user_owned",
        ))
        upload_store.save_chunks("job-g", text_ingest.chunk_text(
            "B.", "b.md",
            source="web_search", license="CC-BY", source_url="https://x/b",
        ))
        before = upload_store.summarize("job-g")
        assert before["chunks"] == 2
        assert before["by_source"] == {"upload": 1, "web_search": 1}

        upload_store.delete_by_filename("job-g", "b.md")
        after = upload_store.summarize("job-g")
        assert after["chunks"] == 1
        assert after["by_source"] == {"upload": 1}
        assert after["by_license"] == {"user_owned": 1}
        assert "https://x/b" not in after["files"]
        assert "a.md" in after["files"]


class TestAtomicRewrite:
    def test_no_orphan_tmp_after_delete(self):
        upload_store.save_chunks("job-h", text_ingest.chunk_text("A.", "a.md"))
        upload_store.save_chunks("job-h", text_ingest.chunk_text("B.", "b.md"))
        upload_store.delete_by_filename("job-h", "a.md")
        tmp = upload_store.upload_dir("job-h") / "uploads.jsonl.tmp"
        assert not tmp.exists()
