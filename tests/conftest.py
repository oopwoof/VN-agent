"""Suite-wide floor: no test may reach a real LLM/image provider.

Why this exists
---------------
On 2026-08-12 `TestWarningsDedup` was chased as a flaky assertion. It was
not flaky — it was making **live Anthropic calls**. The warning text it
failed on was model-authored prose about the test fixture ("providing no
evaluable narrative content"), which the test's own mock — returning
`narrative_findings: []` — cannot produce. Two runs disagreed (4 vs 5
findings) because the model answered differently.

The mechanism is a bypass this repo has now hit four times:

  2026-08-03  image_gen ignored the mock flag
  2026-08-11  `vn-agent generate --mock` patched module attributes but
              never set `mock_mode_var`  (~$0.12)
  2026-08-11  web `_lifespan` patched 5 of 10 agents, never set the
              ContextVar                  (~$0.28)
  2026-08-12  this: `pending_debug.ainvoke_with_pending_debug` re-imports
              `ainvoke_llm` *inside the function body* (pending_debug.py),
              so `mocker.patch("...structure_reviewer.ainvoke_llm")`
              rebinds a name the call never reads

Every one of those was a test or a caller patching a *name* while the real
gate — `mock_mode_var`, which `ainvoke_llm` itself consults — stayed off.
Patching names is whack-a-mole: each new indirection reopens the hole.

So this sets the gate, not a name, and does it for the whole suite. A test
that genuinely wants the real path must opt out explicitly and visibly.

`.env` is why a clean shell is not protection: `services/llm.py` loads it,
so ANTHROPIC_API_KEY et al. are present even when the environment looks
empty. The env scrub below is defence in depth — `mock_mode_var` is the
guarantee.
"""
from __future__ import annotations

import pytest

_PROVIDER_KEY_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "STABILITY_API_KEY",
    "SUNO_API_KEY",
    "VN_ANTHROPIC_API_KEYS",
    "VN_ANTHROPIC_KEYS_SONNET",
    "VN_ANTHROPIC_KEYS_HAIKU",
)


@pytest.fixture(autouse=True)
def _no_billable_calls(request, monkeypatch):
    """Two layers, because they answer different questions.

    **Key stripping — always.** No credentials, no billable call, whatever
    the code does. This alone would have stopped the 2026-08-12 leak, and
    it is non-invasive: code paths run exactly as they would in production.

    **Forcing `mock_mode_var` — almost always.** This is what makes agent
    tests deterministic instead of quietly consulting a live model. But a
    test *about* the gate itself (does mock short-circuit? does the key
    pool rotate? does image dispatch route to img2img?) has to drive the
    var itself — forcing it on short-circuits the very branch under test.
    Those opt out with `@pytest.mark.no_mock_floor` and stay safe on layer
    one, since they patch their providers and have no keys.

    Genuinely billable tests use `@pytest.mark.real_api`, which skips both
    layers. Both markers are grep-able, so "what can spend money" and
    "what runs unmocked" are each one command.
    """
    if request.node.get_closest_marker("real_api"):
        yield
        return

    for var in _PROVIDER_KEY_VARS:
        monkeypatch.delenv(var, raising=False)

    if request.node.get_closest_marker("no_mock_floor"):
        yield
        return

    from vn_agent.services.llm import mock_mode_var

    token = mock_mode_var.set(True)
    try:
        yield
    finally:
        mock_mode_var.reset(token)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_api: test intentionally makes billable provider calls; "
        "exempt from both conftest floor layers",
    )
    config.addinivalue_line(
        "markers",
        "no_mock_floor: test drives mock_mode_var itself (gate/routing "
        "logic under test); keys are still stripped",
    )
