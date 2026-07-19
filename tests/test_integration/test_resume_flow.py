"""P0-resume: exercise the salvage utility + resume flow against the
fixture matrix in tests/fixtures/pipeline_states/.

Zero real API. Zero LLM calls. Every scenario runs offline.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vn_agent.salvage import SalvageError, salvage_run
from vn_agent.schema.script import VNScript

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pipeline_states"


def _copy_fixture(fixture_name: str, tmp_path: Path) -> Path:
    """Copy a fixture directory to tmp_path so tests can mutate freely."""
    src = _FIXTURES / fixture_name
    dst = tmp_path / fixture_name
    shutil.copytree(src, dst)
    return dst


def _load_script(dir_: Path) -> VNScript:
    return VNScript.model_validate_json((dir_ / "vn_script.json").read_text(encoding="utf-8"))


class TestSalvageAlreadyComplete:
    def test_complete_script_says_already_complete(self, tmp_path):
        d = _copy_fixture("post_writer_complete", tmp_path)
        report = salvage_run(d)
        assert report.action == "already_complete"
        assert report.scenes_before == 5
        assert report.dialogue_before == 15  # 3 lines × 5 scenes
        assert report.written == []


class TestSalvageNoSnapshots:
    def test_director_only_is_noop(self, tmp_path):
        d = _copy_fixture("post_director", tmp_path)
        report = salvage_run(d)
        assert report.action == "noop"
        assert report.snapshots_found == 0
        assert report.dialogue_before == 0
        assert report.dialogue_after == 0
        # No writes → vn_script.json byte-unchanged.
        script_bytes_before = (
            (_FIXTURES / "post_director" / "vn_script.json").read_bytes()
        )
        assert (d / "vn_script.json").read_bytes() == script_bytes_before


class TestSalvagePartial:
    def test_partial_overlays_missing_scenes(self, tmp_path):
        d = _copy_fixture("post_writer_partial", tmp_path)
        report = salvage_run(d)
        assert report.action == "merged_snapshots"
        assert report.scenes_after == 5
        # Started with 3/5 populated (3 lines each = 9), added 2 more (6 lines).
        assert report.dialogue_before == 9
        assert report.dialogue_after == 15
        assert report.snapshots_merged == 2

        # Verify on disk.
        recovered = _load_script(d)
        for scene in recovered.scenes:
            assert len(scene.dialogue) == 3, f"Scene {scene.id} not fully populated"

    def test_dry_run_does_not_write(self, tmp_path):
        d = _copy_fixture("post_writer_partial", tmp_path)
        before_bytes = (d / "vn_script.json").read_bytes()
        report = salvage_run(d, write=False)
        assert report.action == "merged_snapshots"
        # Disk untouched.
        assert (d / "vn_script.json").read_bytes() == before_bytes


class TestSalvageLegacyStuck:
    """The specific case that motivated this feature: Writer completed all
    scenes and wrote snapshots, but vn_script.json was never updated with
    dialogue (pre-v4-P0-resume behavior). Salvage rebuilds it."""

    def test_no_flush_reconstructed_from_snapshots(self, tmp_path):
        d = _copy_fixture("post_writer_no_flush", tmp_path)
        report = salvage_run(d)
        assert report.action == "merged_snapshots"
        assert report.dialogue_before == 0
        assert report.dialogue_after == 15
        assert report.snapshots_merged == 5

        recovered = _load_script(d)
        assert all(len(s.dialogue) == 3 for s in recovered.scenes)

    def test_force_reoverlays_complete_scenes(self, tmp_path):
        """force=True re-applies snapshots even when scenes already have
        dialogue (useful when snapshots are known to be more current)."""
        d = _copy_fixture("post_writer_complete", tmp_path)
        report = salvage_run(d, force=True)
        assert report.action == "merged_snapshots"
        assert report.snapshots_merged == 5


class TestSalvageErrors:
    def test_missing_dir_raises(self):
        with pytest.raises(SalvageError):
            salvage_run(Path("/nonexistent/path"))

    def test_empty_dir_raises(self, tmp_path):
        d = _copy_fixture("empty", tmp_path)
        with pytest.raises(SalvageError):
            salvage_run(d)

    def test_corrupt_script_with_snapshots_raises_actionable(self, tmp_path):
        d = _copy_fixture("corrupt_vn_script", tmp_path)
        with pytest.raises(SalvageError) as exc:
            salvage_run(d)
        # Error mentions the missing outline so users know what to restore.
        assert "vn_script" in str(exc.value).lower() or "outline" in str(exc.value).lower()


class TestReportShape:
    def test_report_to_dict_serializable(self, tmp_path):
        d = _copy_fixture("post_writer_partial", tmp_path)
        report = salvage_run(d, write=False)
        d_dict = report.to_dict()
        # Round-trips through JSON — needed by the web endpoint layer.
        json.dumps(d_dict)
        assert d_dict["action"] == "merged_snapshots"
        assert d_dict["scenes_after"] == 5

    def test_written_paths_reported(self, tmp_path):
        d = _copy_fixture("post_writer_partial", tmp_path)
        report = salvage_run(d)
        assert any(str(d / "vn_script.json") in p for p in report.written)


class TestAtomicWrite:
    """The temp+rename pattern in salvage_run + _flush_partial_vn_script
    guards against half-written vn_script.json when the process dies
    mid-write. Regression: if we ever revert to a plain write_text, this
    catches it."""

    def test_no_orphan_tmp_after_success(self, tmp_path):
        d = _copy_fixture("post_writer_partial", tmp_path)
        salvage_run(d)
        assert not (d / "vn_script.json.tmp").exists()
