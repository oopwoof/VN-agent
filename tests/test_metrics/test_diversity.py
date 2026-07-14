"""P0-6 unit tests: diversity index computation."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from vn_agent.assets import text_ingest, upload_store
from vn_agent.metrics import diversity


@pytest.fixture(autouse=True)
def _iso_upload_root(tmp_path, monkeypatch):
    monkeypatch.setenv(upload_store._DATA_UPLOAD_ROOT_ENV, str(tmp_path / "uploads"))
    yield


class TestComputeEmpty:
    def test_all_empty_returns_zeros(self):
        b = diversity.compute()
        assert b.total_assets == 0
        assert b.non_llm == 0
        assert b.diversity_index == 0.0


class TestUploads:
    def test_upload_only_counts(self):
        upload_store.save_chunks("job-a", text_ingest.chunk_text("A.", "a.md"))
        upload_store.save_chunks("job-a", text_ingest.chunk_text("B.", "b.md"))
        b = diversity.compute(job_id="job-a")
        assert b.upload_chunks == 2
        assert b.total_assets == 2
        assert b.diversity_index == 1.0

    def test_web_search_chunks_separated(self):
        upload_store.save_chunks("job-b", text_ingest.chunk_text(
            "wiki excerpt.", "wiki.html",
            source="web_search", license="CC-BY", source_url="https://x",
        ))
        b = diversity.compute(job_id="job-b")
        assert b.web_search_chunks == 1
        assert b.upload_chunks == 0


class TestLibraryHits:
    def test_reads_hits_jsonl(self, tmp_path):
        p = tmp_path / "library_hits.jsonl"
        p.write_text("\n".join([
            json.dumps({"target_id": "bg_school", "asset_id": "bg_school",
                        "license": "CC0", "source": "local_library"}),
            json.dumps({"target_id": "alice_neutral", "asset_id": "sprite_alice",
                        "license": "CC0", "source": "local_library"}),
        ]), encoding="utf-8")
        b = diversity.compute(output_dir=tmp_path)
        assert b.library_hits == 2
        assert set(b.library_hit_targets) == {"bg_school", "alice_neutral"}


class TestLLMSourced:
    def _script_with_scenes(self, bg_prompts: list[str]):
        scenes = []
        for i, prompt in enumerate(bg_prompts):
            scenes.append(SimpleNamespace(
                id=f"s{i}",
                background_id=f"bg_{i}",
                background_prompt=prompt,
            ))
        return SimpleNamespace(scenes=scenes)

    def test_scenes_without_sentinel_counted_as_llm(self):
        bb = {
            "vn_script": self._script_with_scenes([
                "a school interior painted in soft light",
                "a moonlit rooftop at dusk",
            ]),
            "characters": {},
        }
        b = diversity.compute(blackboard=bb)
        assert b.llm_generated_scenes == 2
        assert b.diversity_index == 0.0

    def test_scenes_with_sentinel_not_counted_llm(self):
        bb = {
            "vn_script": self._script_with_scenes([
                "[library:bg_school · CC0 · Kenney] school interior",
                "a moonlit rooftop at dusk",  # LLM
            ]),
            "characters": {},
        }
        b = diversity.compute(blackboard=bb)
        assert b.llm_generated_scenes == 1

    def test_sprites_with_sentinel_not_counted_llm(self):
        sprite_ok = SimpleNamespace(generation_prompt="[library:alice_std · CC0] portrait")
        sprite_llm = SimpleNamespace(generation_prompt="generated portrait")
        char = SimpleNamespace(sprites=[sprite_ok, sprite_llm])
        bb = {"vn_script": None, "characters": {"c1": char}}
        b = diversity.compute(blackboard=bb)
        assert b.llm_generated_sprites == 1


class TestCombined:
    def test_uploads_plus_llm_scenes(self, tmp_path):
        upload_store.save_chunks("job-c", text_ingest.chunk_text("upload text.", "note.md"))
        bb = {
            "vn_script": SimpleNamespace(scenes=[
                SimpleNamespace(background_id="bg_a", background_prompt="a scene"),
                SimpleNamespace(background_id="bg_b", background_prompt="another scene"),
            ]),
            "characters": {},
        }
        b = diversity.compute(job_id="job-c", output_dir=tmp_path, blackboard=bb)
        assert b.upload_chunks == 1
        assert b.llm_generated_scenes == 2
        assert b.total_assets == 3
        # 1 non-LLM / 3 total = 0.333…
        assert 0.33 < b.diversity_index < 0.34

    def test_thirty_percent_target_achieved(self, tmp_path):
        # 3 upload chunks + 1 library hit + 6 LLM scenes = 4 / 10 = 40%
        for i in range(3):
            upload_store.save_chunks("job-d", text_ingest.chunk_text(f"chunk {i}", f"note{i}.md"))
        (tmp_path / "library_hits.jsonl").write_text(
            json.dumps({"target_id": "bg_a", "license": "CC0"}), encoding="utf-8",
        )
        bb = {
            "vn_script": SimpleNamespace(scenes=[
                SimpleNamespace(background_id=f"bg_{i}", background_prompt="LLM scene")
                for i in range(6)
            ]),
            "characters": {},
        }
        b = diversity.compute(job_id="job-d", output_dir=tmp_path, blackboard=bb)
        assert b.diversity_index >= 0.30

    def test_unique_bg_ids_deduped(self):
        # Two scenes sharing a background_id count as ONE LLM asset (not 2).
        bb = {
            "vn_script": SimpleNamespace(scenes=[
                SimpleNamespace(background_id="bg_a", background_prompt="a"),
                SimpleNamespace(background_id="bg_a", background_prompt="a"),
                SimpleNamespace(background_id="bg_b", background_prompt="b"),
            ]),
            "characters": {},
        }
        b = diversity.compute(blackboard=bb)
        assert b.llm_generated_scenes == 2


class TestAnnotate:
    def test_writes_metrics_key(self, tmp_path):
        upload_store.save_chunks("job-e", text_ingest.chunk_text("t.", "t.md"))
        bb = {"vn_script": None, "characters": {}}
        breakdown = diversity.annotate_blackboard(bb, job_id="job-e", output_dir=tmp_path)
        assert bb["metrics"]["diversity_index"] == 1.0
        assert bb["metrics"]["diversity"]["upload_chunks"] == 1
        assert isinstance(breakdown, diversity.DiversityBreakdown)


class TestSentinelRegex:
    def test_matches_library_sentinel(self):
        s = "[library:bg_school · CC0 · Kenney] a school interior"
        assert diversity._LIBRARY_SENTINEL_RE.search(s) is not None

    def test_no_false_positive_on_regular_bracket(self):
        assert diversity._LIBRARY_SENTINEL_RE.search("[note: some regular text]") is None
        assert diversity._LIBRARY_SENTINEL_RE.search("A scene with brackets [in it]") is None
