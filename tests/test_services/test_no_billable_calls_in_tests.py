"""The suite-wide mock floor must actually hold.

Guards the 2026-08-12 finding: `TestWarningsDedup` was making live
Anthropic calls because `pending_debug.ainvoke_with_pending_debug`
re-imports `ainvoke_llm` inside the function body, defeating any
`mocker.patch("<agent module>.ainvoke_llm")`. See `tests/conftest.py`.

These tests assert the property that actually matters — a real provider
client is never constructed — rather than asserting that some particular
name got patched, which is the assumption that failed four times.
"""
from __future__ import annotations

import pytest


class TestFloorIsOnByDefault:
    def test_mock_mode_var_is_set_for_every_test(self):
        from vn_agent.services.llm import mock_mode_var

        assert mock_mode_var.get() is True, (
            "tests/conftest.py must force mock_mode_var on; without it any "
            "code path that reaches ainvoke_llm bills the real account"
        )

    @pytest.mark.parametrize(
        "var",
        ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"],
    )
    def test_provider_keys_are_stripped(self, var, monkeypatch):
        import os

        assert os.environ.get(var) is None, (
            f"{var} is visible to tests. .env is loaded by services/llm.py, "
            "so a clean shell is not protection."
        )


class TestTheBypassPathIsCovered:
    """The exact call shape that leaked: the pending-debug wrapper."""

    @pytest.mark.asyncio
    async def test_pending_debug_wrapper_does_not_reach_a_provider(self, tmp_path):
        from vn_agent.services.pending_debug import ainvoke_with_pending_debug

        # No mocker.patch here on purpose. If the floor works, this returns
        # canned mock content; if it regresses, it makes a real call.
        result = await ainvoke_with_pending_debug(
            "You are a test.",
            "Say something.",
            output_dir=str(tmp_path),
            name="floor_probe",
            model="claude-sonnet-4-6",
            caller="test_no_billable_calls",
        )
        content = getattr(result, "content", result)
        assert content, "wrapper returned nothing — mock path not wired"

    @pytest.mark.asyncio
    async def test_structure_reviewer_runs_without_any_patching(self):
        """The regression that started it: this used to hit the network."""
        from vn_agent.agents.structure_reviewer import run_structure_reviewer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import BranchOption, Scene, VNScript

        scenes = [
            Scene(id="s0", title="S0", description="d", background_id="bg",
                  characters_present=["alice"],
                  branches=[BranchOption(text="go", next_scene_id="s1")]),
            Scene(id="s1", title="S1", description="d", background_id="bg",
                  characters_present=["alice"]),
        ]
        chars = {
            "alice": CharacterProfile(id="alice", name="A", role="p",
                                      personality="", background=""),
        }
        script = VNScript(title="T", description="d", theme="th",
                          start_scene_id="s0", scenes=scenes, world_variables=[])

        result = await run_structure_reviewer(
            {"vn_script": script, "characters": chars, "warnings": [], "errors": []}
        )
        assert "structure_review_passed" in result


class TestOptingOutIsExplicit:
    def test_real_api_marker_is_registered(self, pytestconfig):
        markers = pytestconfig.getini("markers")
        assert any("real_api" in m for m in markers), (
            "the opt-out marker must be declared so `-m real_api` can "
            "answer 'which tests can spend money'"
        )

    # Files allowed to bill. Adding one must be a visible diff, and each
    # must carry its own skipif so an unset key means "skip", never
    # "silently run against the mock and call itself a real-API test".
    _ALLOWED_TO_BILL = {"test_integration/test_real_api.py"}

    def test_opt_outs_match_the_reviewed_allowlist(self):
        from pathlib import Path

        tests_dir = Path(__file__).resolve().parents[1]
        this_file = Path(__file__).resolve()
        found = {
            p.relative_to(tests_dir).as_posix()
            for p in tests_dir.rglob("test_*.py")
            # Skip self: this file names the marker in order to scan for it.
            if p.resolve() != this_file
            and "pytest.mark.real_api" in p.read_text(encoding="utf-8")
        }
        assert found == self._ALLOWED_TO_BILL, (
            f"billable-test set changed: expected {self._ALLOWED_TO_BILL}, "
            f"found {found}. Update the allowlist deliberately."
        )

    # Files that drive mock_mode_var themselves. These do NOT bill — keys
    # are still stripped and providers are patched — but they run the real
    # dispatch code, so the set is worth pinning too.
    _ALLOWED_NO_FLOOR = {
        "test_services/test_image_gen.py",
        "test_services/test_llm.py",
        "test_services/test_llm_mock_context.py",
        "test_cli/test_mock_patch.py",
    }

    def test_no_mock_floor_opt_outs_match_the_reviewed_allowlist(self):
        from pathlib import Path

        tests_dir = Path(__file__).resolve().parents[1]
        this_file = Path(__file__).resolve()
        found = {
            p.relative_to(tests_dir).as_posix()
            for p in tests_dir.rglob("test_*.py")
            if p.resolve() != this_file
            and "pytest.mark.no_mock_floor" in p.read_text(encoding="utf-8")
        }
        assert found == self._ALLOWED_NO_FLOOR, (
            f"no_mock_floor set changed: expected {self._ALLOWED_NO_FLOOR}, "
            f"found {found}. Each opt-out must patch its own providers."
        )

    def test_every_billable_file_also_skips_without_a_key(self):
        """The marker exempts a file from the floor; only a skipif stops it
        from actually spending when someone runs the suite with keys set."""
        from pathlib import Path

        tests_dir = Path(__file__).resolve().parents[1]
        for rel in self._ALLOWED_TO_BILL:
            text = (tests_dir / rel).read_text(encoding="utf-8")
            assert "skipif" in text and "API_KEY" in text, (
                f"{rel} opts out of the mock floor but has no key-based "
                "skipif — it would bill on any machine with a key set"
            )
