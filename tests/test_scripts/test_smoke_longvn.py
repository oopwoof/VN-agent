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
