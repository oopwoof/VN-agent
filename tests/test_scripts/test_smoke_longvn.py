"""Tests for scripts/smoke_longvn.py — Phase 13-2 Step 4b-6.

The script is a real-API harness and CI must not run it end-to-end.
What we DO test is the pure-Python helper that overrides Settings
for benchmark mode — it's the one place a typo would silently produce
a wrong-tier run that costs real money.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_smoke_module():
    """Import scripts/smoke_longvn.py without executing main()."""
    repo_root = Path(__file__).resolve().parents[2]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    spec = importlib.util.spec_from_file_location(
        "smoke_longvn", repo_root / "scripts" / "smoke_longvn.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _SettingsStub:
    """Mimics the three Settings fields _apply_concurrency_overrides touches.
    Construction-time validators don't fire — we're testing post-construction
    mutation, which is exactly what benchmark mode does."""

    def __init__(self):
        self.writer_max_concurrent = 1
        self.enable_thinking_fanout = False
        self.writer_consume_thinking = False


class TestApplyConcurrencyOverrides:
    """Override helper used by both single-trial and benchmark paths."""

    def test_concurrent_1_leaves_thinking_flags_untouched(self):
        """Sequential path doesn't NEED thinking, so we don't force it on
        when the user explicitly asked for concurrent=1."""
        smoke = _load_smoke_module()
        s = _SettingsStub()
        smoke._apply_concurrency_overrides(s, 1)
        assert s.writer_max_concurrent == 1
        assert s.enable_thinking_fanout is False
        assert s.writer_consume_thinking is False

    def test_concurrent_gt_1_flips_thinking_flags(self):
        """Coupling rule: parallel writers without thinking_fanout would
        produce uncoordinated peer dialogue. The helper must auto-enable
        both flags so a benchmark trial doesn't silently degrade."""
        smoke = _load_smoke_module()
        s = _SettingsStub()
        smoke._apply_concurrency_overrides(s, 5)
        assert s.writer_max_concurrent == 5
        assert s.enable_thinking_fanout is True
        assert s.writer_consume_thinking is True

    def test_override_is_idempotent(self):
        """Re-applying the same tier doesn't toggle anything."""
        smoke = _load_smoke_module()
        s = _SettingsStub()
        smoke._apply_concurrency_overrides(s, 3)
        smoke._apply_concurrency_overrides(s, 3)
        assert s.writer_max_concurrent == 3
        assert s.enable_thinking_fanout is True
        assert s.writer_consume_thinking is True

    def test_benchmark_tiers_constant_is_1_2_5(self):
        """Step 4b-6 spec — benchmark explicitly walks 1, 2, 5 so the
        wall-clock comparison is anchored to sequential at the bottom
        and the concurrent=5 ≥1.5x target at the top."""
        smoke = _load_smoke_module()
        assert smoke._BENCHMARK_TIERS == (1, 2, 5)


class _LongformSettingsStub:
    """Fields _apply_longform_overrides touches, at their library defaults."""

    def __init__(self):
        self.enable_cross_ref_sync = False
        self.enable_scene_summarization = False
        self.reviewer_timeout_seconds = 300.0


class TestApplyLongformOverrides:
    """Long-form machinery that ships off by default. This ran on the mock
    path only until 2026-08-24, so paid runs exercised LESS than the free
    dry run — the reason it now applies to both."""

    def test_flags_forced_on(self):
        smoke = _load_smoke_module()
        s = _LongformSettingsStub()
        smoke._apply_longform_overrides(s, 12)
        assert s.enable_cross_ref_sync is True
        assert s.enable_scene_summarization is True

    def test_reviewer_timeout_scales_with_scene_count(self):
        """The dialogue rubric reads every scene in one call, so the
        default sized for ~5 scenes starves a 50-scene run."""
        smoke = _load_smoke_module()
        s = _LongformSettingsStub()
        smoke._apply_longform_overrides(s, 50)
        assert s.reviewer_timeout_seconds == 600.0

    def test_short_run_keeps_configured_timeout(self):
        """12 scenes needs 144s by the formula — never lower the setting."""
        smoke = _load_smoke_module()
        s = _LongformSettingsStub()
        smoke._apply_longform_overrides(s, 12)
        assert s.reviewer_timeout_seconds == 300.0


class TestHealthSignals:
    """Phase 13-3 M0-4: pure-function tests for tier-gating health logic.
    The M1 tiered runner (12 → 25 → 50) breaks on red status; these tests
    pin the threshold semantics so tier-gating policy can't drift silently."""

    def test_clean_run_is_green(self):
        smoke = _load_smoke_module()
        signals, status = smoke._compute_health_signals(
            n_rotations=0, scene_count=12, wall_minutes=3.5,
        )
        assert signals == []
        assert status == "green"

    def test_few_rotations_is_green(self):
        """≤5 rotations + density ≤1 + reasonable wall = green."""
        smoke = _load_smoke_module()
        signals, status = smoke._compute_health_signals(
            n_rotations=3, scene_count=25, wall_minutes=6.0,
        )
        assert signals == []
        assert status == "green"

    def test_too_many_rotations_is_red(self):
        """>5 rotations is the hard abort — burns credits with no signal."""
        smoke = _load_smoke_module()
        signals, status = smoke._compute_health_signals(
            n_rotations=10, scene_count=50, wall_minutes=10.0,
        )
        assert any("retry_count=10" in s for s in signals)
        assert status == "red"

    def test_high_density_alone_is_yellow(self):
        """Density >1/scene without other signals = advisory (yellow)."""
        smoke = _load_smoke_module()
        # 4 scenes, 5 rotations → density 1.25 but rotations not >5
        # (boundary: rotations=5 ≤ threshold, density 5/4>1 fires)
        signals, status = smoke._compute_health_signals(
            n_rotations=5, scene_count=4, wall_minutes=2.0,
        )
        assert any("key_rotation_density=5/4" in s for s in signals)
        # density alone should NOT escalate to red
        assert status == "yellow"

    def test_wall_blowout_is_red(self):
        """>2x expected wall time = red. 12 scenes expected 15 min, so
        the red line is 30 min and 35 is past it."""
        smoke = _load_smoke_module()
        signals, status = smoke._compute_health_signals(
            n_rotations=0, scene_count=12, wall_minutes=35.0,
        )
        assert any("> 2x expected" in s for s in signals)
        assert status == "red"

    def test_measured_real_throughput_is_green(self):
        """The one real run on record — 6 scenes, 6.2 min (61s/scene) —
        scored RED under the original 18s/scene guess. With
        --abort-on-degradation that would have killed the expensive tier
        over ordinary throughput, so the baseline now covers it."""
        smoke = _load_smoke_module()
        signals, status = smoke._compute_health_signals(
            n_rotations=0, scene_count=6, wall_minutes=6.2,
        )
        assert all("> 2x expected" not in s for s in signals)
        assert status == "green"

    def test_short_run_minimum_floor_for_wall_threshold(self):
        """Tiny runs are dominated by fixed setup cost, so the expected
        wall floors at 5 min — a 2-min single-scene run is fine."""
        smoke = _load_smoke_module()
        signals, status = smoke._compute_health_signals(
            n_rotations=0, scene_count=1, wall_minutes=2.0,
        )
        assert all("> 2x expected" not in s for s in signals)
        assert status == "green"

    def test_red_dominates_yellow(self):
        """When both red and yellow signals fire, status is red."""
        smoke = _load_smoke_module()
        # rotations 10 (red) + density 10/8>1 (yellow)
        signals, status = smoke._compute_health_signals(
            n_rotations=10, scene_count=8, wall_minutes=4.0,
        )
        assert len(signals) == 2
        assert status == "red"


class TestMockStructuralIssues:
    """50-scene dry run P4: pure predicate behind the --mock assertions.

    The mock tiers can't assert on cost or cache ratio (both zero), so
    they assert on structure instead: distinct dialogue per scene,
    non-vacuous thinking, prose chapter rollups. This helper is the
    testable core; the script merges its FAIL strings into the standard
    assertion list."""

    def _script(self, *, duplicate_dialogue=False, vacuous_thinking=False,
                rollup_is_json=False):
        from vn_agent.schema.script import (
            Chapter, DialogueLine, Scene, SceneThinking, VNScript,
        )

        scenes = []
        for i in range(3):
            text = "same line" if duplicate_dialogue else f"line for s{i:02d}"
            scenes.append(Scene(
                id=f"s{i:02d}", title=f"S{i}", description="d",
                background_id="bg",
                dialogue=[DialogueLine(character_id=None, text=text)],
                thinking=None if vacuous_thinking else SceneThinking(
                    writing_intent=f"intent {i}",
                ),
            ))
        chapters = [Chapter(
            chapter_id="ch01", scene_ids=[s.id for s in scenes],
            summary='[{"character_id": null}]' if rollup_is_json
            else "A prose chapter summary long enough to look like prose.",
        )]
        return VNScript(
            title="T", description="d", theme="t", start_scene_id="s00",
            scenes=scenes, chapters=chapters,
        )

    def test_clean_script_yields_no_issues(self):
        smoke = _load_smoke_module()
        issues = smoke._mock_structural_issues(
            self._script(), expect_thinking=True,
        )
        assert issues == []

    def test_duplicate_dialogue_flagged(self):
        smoke = _load_smoke_module()
        issues = smoke._mock_structural_issues(
            self._script(duplicate_dialogue=True), expect_thinking=True,
        )
        assert any("identical" in i for i in issues)

    def test_vacuous_thinking_flagged_only_when_expected(self):
        smoke = _load_smoke_module()
        script = self._script(vacuous_thinking=True)
        with_expect = smoke._mock_structural_issues(script, expect_thinking=True)
        without_expect = smoke._mock_structural_issues(script, expect_thinking=False)
        assert any("thinking" in i for i in with_expect)
        assert not any("thinking" in i for i in without_expect)

    def test_json_rollup_flagged_as_misroute(self):
        smoke = _load_smoke_module()
        issues = smoke._mock_structural_issues(
            self._script(rollup_is_json=True), expect_thinking=True,
        )
        assert any("rollup" in i or "summary" in i for i in issues)


class TestOutputDirArg:
    """--output-dir lets a multi-tier run keep its artifacts under one
    root (demo_output/real_<date>/tier_12, tier_50) instead of scattered
    timestamp siblings. _run() already accepted an output_subdir kwarg
    (benchmark mode uses it); this exposes it on the CLI.

    These drive the real main() rather than a hand-rolled parser, so a
    flag that parses but never reaches _run still fails the test.
    """

    def _run_main(self, monkeypatch, argv):
        """Call main() with _run faked out, returning the captured kwargs.

        main() rewraps sys.stdout/stderr for UTF-8 on win32, which would
        corrupt pytest's capture bookkeeping for the rest of the process
        (the same hazard that keeps that block out of module scope), so
        we make the platform check fall through for the call.
        """
        smoke = _load_smoke_module()
        monkeypatch.setattr(sys, "platform", "linux")
        captured: dict = {}

        async def _fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return {"assertions": [], "health_status": "green"}

        monkeypatch.setattr(smoke, "_run", _fake_run)
        monkeypatch.setattr(sys, "argv", ["smoke_longvn.py", *argv])
        smoke.main()
        return captured

    def test_output_dir_reaches_run(self, monkeypatch, tmp_path):
        target = tmp_path / "real_20260824" / "tier_12"
        captured = self._run_main(
            monkeypatch, ["--mock", "--scenes", "12", "--output-dir", str(target)],
        )
        assert captured["kwargs"]["output_subdir"] == target

    def test_omitted_flag_leaves_auto_timestamp_path(self, monkeypatch):
        """None keeps the existing demo_output/smoke_longvn_<UTC>/ behavior."""
        captured = self._run_main(monkeypatch, ["--mock", "--scenes", "12"])
        assert captured["kwargs"]["output_subdir"] is None


class TestCountJsonlLines:
    """Rotation counting must be a per-run delta: api_key_rotations.jsonl is
    cumulative across every run in the CWD, so reading its absolute size
    attributed 47 historic rotations to a zero-call mock run and flipped
    health to RED. The helper is the countable half; _run snapshots it
    before/after the graph."""

    def test_missing_file_counts_zero(self, tmp_path):
        smoke = _load_smoke_module()
        assert smoke._count_jsonl_lines(tmp_path / "nope.jsonl") == 0

    def test_blank_lines_ignored(self, tmp_path):
        smoke = _load_smoke_module()
        p = tmp_path / "r.jsonl"
        p.write_text('{"a":1}\n\n{"b":2}\n   \n', encoding="utf-8")
        assert smoke._count_jsonl_lines(p) == 2
