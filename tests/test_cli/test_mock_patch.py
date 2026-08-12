"""Regression guard for a real cost-safety bug found 2026-07-26/27:
`vn-agent generate --mock` made 5 real Anthropic API calls (~$0.12) because
`agents/reviewer.py`/`structure_reviewer.py` route their actual LLM call
through `services/pending_debug.py::ainvoke_with_pending_debug()`, which
does its own fresh `from vn_agent.services.llm import ainvoke_llm` import —
bypassing `_patch_mock_llm()`'s static per-module monkey-patch entirely.

Fix: `_patch_mock_llm()` also sets the `mock_mode_var` ContextVar that
`ainvoke_llm` itself checks internally, so every call path — including ones
that route around the static patch list via their own fresh import — still
short-circuits into the mock. These tests exist so this gap cannot silently
regress; they must never make a real network call themselves.
"""
from __future__ import annotations

import time

import pytest

from vn_agent.cli import _patch_mock_llm, _unpatch_mock_llm
from vn_agent.services.llm import mock_mode_var
from vn_agent.services.pending_debug import ainvoke_with_pending_debug

# Asserts that _patch_mock_llm is what sets mock_mode_var, and that
# _unpatch resets it. The conftest floor pre-setting the var would make
# both assertions vacuous.
pytestmark = pytest.mark.no_mock_floor

# No shared autouse fixture here: pytest-asyncio runs each async test body in
# its own task context, and a ContextVar token set in that context can't be
# reset from a plain sync fixture's teardown ("Token was created in a
# different Context"). Every test below patches and unpatches itself, in a
# try/finally, within its own context.


class TestPatchMockLlmSetsContextVar:
    def test_patch_sets_mock_mode_var(self):
        assert mock_mode_var.get() is False
        _patch_mock_llm()
        try:
            assert mock_mode_var.get() is True
        finally:
            _unpatch_mock_llm()

    def test_unpatch_resets_mock_mode_var(self):
        _patch_mock_llm()
        _unpatch_mock_llm()
        assert mock_mode_var.get() is False


class TestPendingDebugBypassIsCovered:
    """The actual regression: ainvoke_with_pending_debug (Reviewer's real
    call path) must route to the mock once _patch_mock_llm() has run, even
    though it never touches the module-level patched name."""

    async def test_reviewer_path_via_pending_debug_uses_mock(self, tmp_path):
        _patch_mock_llm()
        try:
            t0 = time.monotonic()
            result = await ainvoke_with_pending_debug(
                "You are a reviewer. Score the dialogue.",
                "Score this scene.",
                output_dir=str(tmp_path),
                name="reviewer_regression_check",
                caller="reviewer",
            )
            elapsed = time.monotonic() - t0
        finally:
            _unpatch_mock_llm()

        # A real network round-trip cannot complete this fast; the mock
        # fixture dispatch is pure in-memory string lookup.
        assert elapsed < 2.0, (
            f"took {elapsed:.2f}s — looks like a real network call was made, "
            "not a mock short-circuit"
        )
        content = getattr(result, "content", str(result))
        assert content  # canned reviewer fixture is non-empty
