"""P0-8: end-to-end integration for the v4 multi-source material fusion flow.

Bundles upload + web-search + library + dedup + license gate + diversity
so a single test proves the modules cooperate correctly. Everything runs
against fixtures / mocks — no network, no LLM API cost. Marked with a
plain integration path (no @pytest.mark.slow) so CI picks it up.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vn_agent.assets import (
    dedup,
    library,
    license_gate,
    text_ingest,
    upload_store,
    web_search_agent,
)
from vn_agent.assets.web_search_agent import SearchResult, StaticFixtureProvider
from vn_agent.metrics import diversity


@pytest.fixture
def job_env(tmp_path, monkeypatch):
    """Isolated upload root + output_dir + a small asset library."""
    monkeypatch.setenv(upload_store._DATA_UPLOAD_ROOT_ENV, str(tmp_path / "uploads"))
    output_dir = tmp_path / "run"
    output_dir.mkdir()

    # A tiny library that will hit for "school" / "校园" queries.
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "school_day.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (lib_dir / "school_night.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    manifest = lib_dir / "manifest.json"
    manifest.write_text(json.dumps({
        "$schema_version": 1,
        "assets": [
            {
                "id": "bg_school_day",
                "type": "background",
                "path": "school_day.png",
                "license": "CC0",
                "attribution": "Kenney (Public Domain)",
                "tags": ["school", "classroom", "day", "校园", "白天"],
            },
            {
                "id": "bg_school_night",
                "type": "background",
                "path": "school_night.png",
                "license": "CC-BY",
                "attribution": "OpenGameArt",
                "tags": ["school", "night", "校园", "夜晚"],
            },
        ],
    }), encoding="utf-8")
    monkeypatch.setenv(library._DEFAULT_MANIFEST_ENV, str(manifest))

    return SimpleNamespace(
        tmp=tmp_path,
        output_dir=output_dir,
        manifest=manifest,
        job_id="job-e2e",
    )


class TestUploadFlow:
    def test_upload_persists_and_summarizes(self, job_env):
        # Simulate creator uploading a Chinese world-building doc.
        chunks = text_ingest.chunk_text(
            "背景设定：故事发生在江南水乡的一所高中，主角小明是新转学生。",
            "世界观.md",
            source="upload",
            license="user_owned",
        )
        upload_store.save_chunks(job_env.job_id, chunks)

        loaded = upload_store.load_chunks(job_env.job_id)
        assert loaded and loaded[0].scope == "user_upload"
        assert loaded[0].source_meta["source"] == "upload"
        assert loaded[0].source_meta["cjk_dominant"] is True

        summary = upload_store.summarize(job_env.job_id)
        assert summary["chunks"] == len(loaded)
        assert summary["by_source"] == {"upload": len(loaded)}


class TestWebSearchToUploadStore:
    @pytest.mark.asyncio
    async def test_web_search_chunks_land_in_upload_store(self, job_env):
        provider = StaticFixtureProvider(
            search_map={
                "school": [
                    SearchResult(url="https://wiki/high_school_jp",
                                 title="Japanese High School", snippet="s"),
                ],
            },
            body_map={
                "https://wiki/high_school_jp": (
                    "Japanese high schools follow a 3-year curriculum. "
                    "Cherry-blossom season marks the entrance ceremony."
                ),
            },
        )

        async def planner(topic, max_queries=5):  # noqa: ARG001
            return ["school culture"]

        report = await web_search_agent.search_and_ingest(
            topic="school culture",
            job_id=job_env.job_id,
            provider=provider,
            query_planner=planner,
        )
        assert report.stopped_reason == "ok"
        assert report.chunks_ingested >= 1

        # The persisted chunk carries web_search provenance.
        all_chunks = upload_store.load_chunks(job_env.job_id)
        web = [c for c in all_chunks if c.source_meta["source"] == "web_search"]
        assert web
        assert web[0].source_meta["source_url"].startswith("https://wiki/")
        assert "search_query" in web[0].source_meta


class TestLibraryHit:
    def test_hit_copies_file_and_records_provenance(self, job_env):
        target = job_env.output_dir / "game/images/backgrounds/bg_class.png"
        hit = library.try_library_hit("校园 白天", "background", target)
        assert hit is not None
        assert hit.id == "bg_school_day"
        # File was copied into the output_dir.
        assert target.exists()

        # Record hit → library_hits.jsonl (what diversity index reads).
        library.record_library_hit(
            job_env.output_dir, "background", "bg_class", hit, query="校园 白天",
        )
        hits_path = job_env.output_dir / "library_hits.jsonl"
        assert hits_path.exists()
        first = json.loads(hits_path.read_text(encoding="utf-8").splitlines()[0])
        assert first["asset_id"] == "bg_school_day"
        assert first["license"] == "CC0"


class TestDedup:
    def test_upload_and_web_dedup_collapses_repeat_body(self, job_env):
        body = "The Edo period lasted from 1603 to 1867."
        upload_chunks = text_ingest.chunk_text(body, "notes.md", source="upload")
        web_chunks = text_ingest.chunk_text(
            body, "wiki-edo.html",
            source="web_search", source_url="https://wiki/edo", search_query="edo",
        )
        upload_store.save_chunks(job_env.job_id, upload_chunks)
        upload_store.save_chunks(job_env.job_id, web_chunks)

        # Load everything, then run dedup — identical body collapses.
        all_chunks = upload_store.load_chunks(job_env.job_id)
        kept, dropped = dedup.dedup_chunks(all_chunks)
        assert len(kept) == 1
        assert len(dropped) >= 1


class TestLicenseGate:
    def test_pass_with_only_accepted_licenses(self, job_env):
        upload_store.save_chunks(job_env.job_id, text_ingest.chunk_text(
            "clean.", "clean.md", license="user_owned",
        ))
        # Record a library hit (CC0) so gate sees both sources.
        target = job_env.output_dir / "game/images/backgrounds/bg_a.png"
        hit = library.try_library_hit("校园", "background", target)
        assert hit is not None
        library.record_library_hit(job_env.output_dir, "background", "bg_a", hit)

        report = license_gate.audit(
            upload_chunks=upload_store.load_chunks(job_env.job_id),
            library_hits_path=job_env.output_dir / "library_hits.jsonl",
        )
        assert report.ok
        assert set(report.by_license) <= license_gate.ACCEPTED_LICENSES

    def test_unknown_license_blocks_enforce(self, job_env):
        upload_store.save_chunks(job_env.job_id, text_ingest.chunk_text(
            "flagged.", "flagged.md", license="GPL-3.0",
        ))
        with pytest.raises(license_gate.LicenseGateError):
            license_gate.enforce(
                upload_chunks=upload_store.load_chunks(job_env.job_id),
            )


class TestDiversityTarget:
    def test_upload_plus_library_hits_p0_target(self, job_env):
        """1 upload + 1 library hit + 2 LLM scenes = 2/4 = 50% ≥ 30% target."""
        # Upload
        upload_store.save_chunks(job_env.job_id, text_ingest.chunk_text(
            "user notes.", "notes.md",
        ))
        # Library hit
        target = job_env.output_dir / "game/images/backgrounds/bg_a.png"
        hit = library.try_library_hit("校园", "background", target)
        library.record_library_hit(job_env.output_dir, "background", "bg_a", hit)

        # Fake VN blackboard with 2 LLM-generated scenes (no [library:...] sentinel).
        blackboard = {
            "vn_script": SimpleNamespace(scenes=[
                SimpleNamespace(background_id="bg_llm_1", background_prompt="a scene"),
                SimpleNamespace(background_id="bg_llm_2", background_prompt="another scene"),
            ]),
            "characters": {},
        }
        breakdown = diversity.annotate_blackboard(
            blackboard,
            job_id=job_env.job_id,
            output_dir=job_env.output_dir,
        )
        assert breakdown.diversity_index >= 0.30
        # Also written to the blackboard's metrics dict.
        assert blackboard["metrics"]["diversity_index"] == breakdown.diversity_index
        assert blackboard["metrics"]["diversity"]["non_llm"] == 2
        assert blackboard["metrics"]["diversity"]["llm"] == 2

    def test_all_llm_gives_zero_diversity(self, job_env):
        blackboard = {
            "vn_script": SimpleNamespace(scenes=[
                SimpleNamespace(background_id=f"bg_{i}", background_prompt="LLM prompt")
                for i in range(3)
            ]),
            "characters": {},
        }
        breakdown = diversity.annotate_blackboard(
            blackboard,
            job_id=job_env.job_id,
            output_dir=job_env.output_dir,
        )
        assert breakdown.diversity_index == 0.0


class TestFullFusionFlow:
    @pytest.mark.asyncio
    async def test_upload_plus_search_plus_library_plus_metrics(self, job_env):
        # 1) Creator uploads a text doc.
        upload_store.save_chunks(job_env.job_id, text_ingest.chunk_text(
            "小明是新转学生，故事在江南水乡展开。",
            "背景.md",
            license="user_owned",
        ))

        # 2) Web search agent adds two more chunks from a fixture provider.
        provider = StaticFixtureProvider(
            search_map={
                "sakura": [SearchResult(url="https://wiki/sakura", title="Cherry", snippet="s")],
            },
            body_map={"https://wiki/sakura": "The sakura marks the entrance ceremony."},
        )

        async def planner(topic, max_queries=5):  # noqa: ARG001
            return ["sakura ceremony"]

        await web_search_agent.search_and_ingest(
            topic="cherry blossom school ceremony",
            job_id=job_env.job_id,
            provider=provider,
            query_planner=planner,
        )

        # 3) Library hit records one open-source background.
        target = job_env.output_dir / "game/images/backgrounds/bg_op.png"
        hit = library.try_library_hit("校园 白天", "background", target)
        library.record_library_hit(job_env.output_dir, "background", "bg_op", hit)

        # 4) Blackboard with mixed scenes: one librar-sourced (sentinel), one LLM.
        blackboard = {
            "vn_script": SimpleNamespace(scenes=[
                SimpleNamespace(
                    background_id="bg_op",
                    background_prompt=f"[library:{hit.id} · CC0] school corridor",
                ),
                SimpleNamespace(
                    background_id="bg_llm",
                    background_prompt="a moonlit rooftop",
                ),
            ]),
            "characters": {},
        }
        breakdown = diversity.annotate_blackboard(
            blackboard, job_id=job_env.job_id, output_dir=job_env.output_dir,
        )

        # 5) End-state assertions.
        assert breakdown.upload_chunks >= 1
        assert breakdown.web_search_chunks >= 1
        assert breakdown.library_hits >= 1
        assert breakdown.llm_generated_scenes == 1  # only bg_llm, bg_op has sentinel
        # Non-LLM > LLM → far above the 30% target.
        assert breakdown.diversity_index > 0.30

        # 6) License gate: unknown-license web chunks trigger a violation
        # (best-effort license default for web search is "unknown"). This
        # is the intended shape — creator/reviewer approves before publish.
        report = license_gate.audit(
            upload_chunks=upload_store.load_chunks(job_env.job_id),
            library_hits_path=job_env.output_dir / "library_hits.jsonl",
        )
        assert not report.ok
        assert any(v.source == "web_search" for v in report.violations)
