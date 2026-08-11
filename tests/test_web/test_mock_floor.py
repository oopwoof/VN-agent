"""VN_AGENT_MOCK=1 must be a hard floor on every billable call path.

Regression guard for a real incident (2026-08-11, ~$0.28 of unintended
Anthropic spend): `_lifespan` patched `ainvoke_llm` on only 5 of the 10
agents that import it, and never set `mock_mode_var`. Because the frontend
sends `mock: false` by default, a server started with `VN_AGENT_MOCK=1`
still made real calls through structure_reviewer / state_orchestrator /
thinking / summarizer, and did not block image generation at all —
`image_gen.py` gates solely on `mock_mode_var`.

The fix makes the env var floor the per-request flag in `_resolve_mock`,
so the single ContextVar every billable path already consults is forced on.
"""
from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "vn_agent"


def _reload_app_with_env(monkeypatch, value: str | None):
    """Re-import web.app so the module-level _MOCK_MODE re-reads the env."""
    if value is None:
        monkeypatch.delenv("VN_AGENT_MOCK", raising=False)
    else:
        monkeypatch.setenv("VN_AGENT_MOCK", value)
    import vn_agent.web.app as app_module
    return importlib.reload(app_module)


class TestEnvVarIsAHardFloor:
    @pytest.mark.parametrize("env_value", ["1", "true", "TRUE", "yes"])
    def test_env_var_forces_mock_on_despite_request_saying_false(self, monkeypatch, env_value):
        """The exact shape of the incident: env set, body says mock:false."""
        app_module = _reload_app_with_env(monkeypatch, env_value)
        assert app_module._resolve_mock(False) is True

    def test_env_var_also_leaves_an_explicit_true_alone(self, monkeypatch):
        app_module = _reload_app_with_env(monkeypatch, "1")
        assert app_module._resolve_mock(True) is True

    def test_without_the_env_var_the_request_still_decides(self, monkeypatch):
        """The floor must not change the existing contract when unset."""
        app_module = _reload_app_with_env(monkeypatch, None)
        assert app_module._resolve_mock(False) is False
        assert app_module._resolve_mock(True) is True

    def test_env_var_can_never_force_mock_off(self, monkeypatch):
        """A floor, not an override: it raises, never lowers."""
        app_module = _reload_app_with_env(monkeypatch, "0")
        assert app_module._resolve_mock(True) is True


class TestEveryBillablePathIsCovered:
    """The floor is only a guarantee if every call site actually applies it."""

    def test_no_call_site_bypasses_the_floor(self):
        """`mock_mode_var.set(bool(...))` was the bug. Ban the raw form."""
        source = (SRC / "web" / "app.py").read_text(encoding="utf-8")
        # Match the assignment form only — prose in docstrings mentions
        # `mock_mode_var.set(...)` and must not be mistaken for a call site.
        setters = [
            line.strip()
            for line in source.splitlines()
            if "= mock_mode_var.set(" in line
        ]
        assert setters, "expected at least one mock_mode_var.set call site"
        offenders = [s for s in setters if "_resolve_mock(" not in s]
        assert not offenders, (
            "these call sites set mock_mode_var without the VN_AGENT_MOCK floor, "
            f"reopening the 2026-08-11 spend hole: {offenders}"
        )

    def test_all_agents_importing_ainvoke_llm_are_covered_by_the_contextvar(self):
        """Derive the agent list from disk so a NEW agent cannot reopen the gap.

        This deliberately does not assert against `_lifespan`'s patch list:
        that list is defence in depth and is allowed to be partial. The
        guarantee comes from `mock_mode_var`, which `ainvoke_llm` consults
        for every caller — so what matters is that agents go through
        `ainvoke_llm` rather than calling a provider SDK directly.
        """
        agents_dir = SRC / "agents"
        importers = sorted(
            p.name
            for p in agents_dir.glob("*.py")
            if "from vn_agent.services.llm import" in p.read_text(encoding="utf-8")
        )
        assert importers, "expected some agents to import from services.llm"

        for name in importers:
            text = (agents_dir / name).read_text(encoding="utf-8")
            for forbidden in ("import anthropic", "import openai", "from anthropic", "from openai"):
                assert forbidden not in text, (
                    f"{name} reaches a provider SDK directly, bypassing the "
                    f"mock_mode_var gate in ainvoke_llm: {forbidden!r}"
                )


class TestStartupBannerMakesTheGateVisible:
    """An operator must be able to read the mock state before a live demo.

    `_lifespan` logs it via `logger.info`, but uvicorn configures handlers
    only for its own loggers, so this module's INFO records are dropped
    before reaching a terminal — the runbook's "check the startup log"
    instruction pointed at a line that never appeared. Both spend incidents
    started with someone believing mock was on, so the banner is printed.
    """

    @pytest.mark.parametrize(
        ("env_value", "expected"), [("1", "ON"), (None, "OFF")]
    )
    def test_lifespan_prints_the_effective_mock_state(self, monkeypatch, capsys, env_value, expected):
        app_module = _reload_app_with_env(monkeypatch, env_value)

        async def drive():
            async with app_module._lifespan(app_module.app):
                pass

        asyncio.run(drive())

        banner = [ln for ln in capsys.readouterr().out.splitlines() if "[vn-agent]" in ln]
        assert banner, "startup must print the mock state to stdout, not only log it"
        assert expected in banner[0], f"expected mock floor {expected} in {banner[0]!r}"


class TestImageGenerationSharesTheSameGate:
    def test_image_gen_gates_on_mock_mode_var(self):
        """Image generation was the unguarded half of the 2026-08-03 incident."""
        text = (SRC / "services" / "image_gen.py").read_text(encoding="utf-8")
        assert "mock_mode_var" in text, (
            "image_gen.py must consult mock_mode_var, otherwise VN_AGENT_MOCK "
            "cannot block billable image calls"
        )
