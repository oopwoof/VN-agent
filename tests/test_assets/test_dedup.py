"""P0-3 unit tests: cross-source deduplication."""
from __future__ import annotations

import pytest

from vn_agent.assets import dedup, text_ingest


def _sim_embed(text: str, offset: float = 0.0) -> list[float]:
    """Toy embedding: 4-dim vector deterministically derived from text.

    Not semantically meaningful — just enough to test the cosine gate.
    """
    tokens = text.lower().split()
    a = sum(len(t) for t in tokens) / max(len(tokens), 1)
    b = sum(1 for t in tokens if any(c in "aeiou" for c in t)) / max(len(tokens), 1)
    return [a + offset, b, len(tokens) * 0.1, offset]


class TestTextFingerprint:
    def test_identical_text_same_hash(self):
        idx = dedup.DedupIndex()
        fp1 = idx.fingerprint_text("A quiet village.")
        fp2 = idx.fingerprint_text("A quiet village.")
        assert fp1.key == fp2.key

    def test_whitespace_and_case_normalized(self):
        idx = dedup.DedupIndex()
        fp1 = idx.fingerprint_text("A Quiet Village.")
        fp2 = idx.fingerprint_text("a  quiet    village.")
        assert fp1.key == fp2.key

    def test_different_text_different_hash(self):
        idx = dedup.DedupIndex()
        fp1 = idx.fingerprint_text("Hello.")
        fp2 = idx.fingerprint_text("Goodbye.")
        assert fp1.key != fp2.key


class TestRegister:
    def test_first_registration_is_novel(self):
        idx = dedup.DedupIndex()
        fp = idx.fingerprint_text("Hello.")
        assert idx.register(fp) is True

    def test_exact_duplicate_rejected(self):
        idx = dedup.DedupIndex()
        idx.register(idx.fingerprint_text("Hello.", origin="a"))
        assert idx.register(idx.fingerprint_text("Hello.", origin="b")) is False
        # Skipped list records what matched.
        assert idx.skipped[-1][0].origin == "b"
        assert idx.skipped[-1][1] == "a"

    def test_none_fingerprint_passes_through(self):
        # When fingerprinting fails (e.g. missing imagehash), we don't block.
        assert dedup.DedupIndex().register(None) is True


class TestEmbeddingDedup:
    def test_near_dup_rejected(self):
        idx = dedup.DedupIndex()
        # Two texts with slightly different phrasing but same toy embedding.
        assert idx.register_text_with_embedding("A quiet village.", [1.0, 0.5, 0.2, 0.1], origin="a") is True
        assert idx.register_text_with_embedding("A quiet town.", [1.0, 0.5, 0.2, 0.1], origin="b") is False

    def test_below_threshold_kept(self):
        idx = dedup.DedupIndex()
        assert idx.register_text_with_embedding("First text.", [1.0, 0.0, 0.0, 0.0], origin="a") is True
        # Orthogonal → cosine 0 → keep.
        assert idx.register_text_with_embedding("Different text.", [0.0, 1.0, 0.0, 0.0], origin="b") is True

    def test_missing_embedding_falls_back_to_sha(self):
        idx = dedup.DedupIndex()
        assert idx.register_text_with_embedding("Text A.", None, origin="a") is True
        assert idx.register_text_with_embedding("Text A.", None, origin="b") is False
        assert idx.register_text_with_embedding("Text B.", None, origin="c") is True


class TestDedupChunks:
    def test_exact_duplicates_dropped_preserving_order(self):
        chunks = [
            *text_ingest.chunk_text("Alpha paragraph.", "a.md"),
            *text_ingest.chunk_text("Beta paragraph.", "b.md"),
            *text_ingest.chunk_text("Alpha paragraph.", "c.md"),  # dup of first
        ]
        kept, dropped = dedup.dedup_chunks(chunks)
        assert len(kept) == 2
        assert len(dropped) == 1
        assert kept[0].source_meta["filename"] == "a.md"
        assert kept[1].source_meta["filename"] == "b.md"
        assert dropped[0][0].source_meta["filename"] == "c.md"

    def test_no_duplicates_all_kept(self):
        chunks = [
            *text_ingest.chunk_text("First.", "a.md"),
            *text_ingest.chunk_text("Second.", "b.md"),
        ]
        kept, dropped = dedup.dedup_chunks(chunks)
        assert len(kept) == 2
        assert dropped == []

    def test_near_dup_dropped_with_embed_fn(self):
        chunks = [
            *text_ingest.chunk_text("The quiet village.", "a.md"),
            *text_ingest.chunk_text("The quiet town.", "b.md"),
        ]
        # Same embedding for both → cosine 1.0 → dedup fires.
        kept, dropped = dedup.dedup_chunks(chunks, embed_fn=lambda _: [1.0, 0.0, 0.0])
        assert len(kept) == 1
        assert len(dropped) == 1


class TestImagePHash:
    def test_missing_imagehash_returns_none(self, monkeypatch, tmp_path):
        # Force the ImportError branch by hiding imagehash from importlib.
        import sys

        monkeypatch.setitem(sys.modules, "imagehash", None)
        idx = dedup.DedupIndex()
        # Create a dummy path — never opened because ImportError fires first.
        assert idx.fingerprint_image(tmp_path / "not_real.png", origin="x") is None

    def test_two_identical_pngs_deduped(self, tmp_path):
        pytest.importorskip("imagehash")
        pytest.importorskip("PIL")
        from PIL import Image

        p1 = tmp_path / "a.png"
        p2 = tmp_path / "b.png"
        Image.new("RGB", (32, 32), color=(200, 100, 50)).save(p1)
        Image.new("RGB", (32, 32), color=(200, 100, 50)).save(p2)

        idx = dedup.DedupIndex()
        assert idx.register(idx.fingerprint_image(p1, origin="a")) is True
        assert idx.register(idx.fingerprint_image(p2, origin="b")) is False

    def test_visually_different_pngs_kept(self, tmp_path):
        pytest.importorskip("imagehash")
        pytest.importorskip("PIL")
        from PIL import Image

        p1 = tmp_path / "a.png"
        p2 = tmp_path / "b.png"
        # Solid vs checker → very different pHash.
        Image.new("RGB", (32, 32), color=(200, 100, 50)).save(p1)
        img = Image.new("RGB", (32, 32), color=(255, 255, 255))
        for x in range(0, 32, 4):
            for y in range(0, 32, 4):
                if (x + y) % 8 == 0:
                    for dx in range(4):
                        for dy in range(4):
                            img.putpixel((x + dx, y + dy), (0, 0, 0))
        img.save(p2)

        idx = dedup.DedupIndex()
        assert idx.register(idx.fingerprint_image(p1, origin="a")) is True
        assert idx.register(idx.fingerprint_image(p2, origin="b")) is True


class TestNormalize:
    def test_empty_stays_empty(self):
        assert dedup._normalize_text("") == ""
        assert dedup._normalize_text(None) == ""  # type: ignore[arg-type]

    def test_cosine_orthogonal(self):
        assert dedup._cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_cosine_identical(self):
        assert dedup._cosine([1.0, 2.0], [1.0, 2.0]) == pytest.approx(1.0)

    def test_cosine_degenerate(self):
        assert dedup._cosine([], [1.0]) == 0.0
        assert dedup._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
