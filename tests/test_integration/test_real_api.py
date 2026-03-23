"""Real API smoke test — only runs when ANTHROPIC_API_KEY is set.

Usage:
    uv run pytest tests/test_integration/test_real_api.py -m slow -v
"""
from __future__ import annotations

import os

import pytest

from vn_agent.agents.graph import build_graph
from vn_agent.agents.state import initial_state

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set — skipping real API test",
    ),
]


@pytest.mark.asyncio
async def test_real_api_text_only():
    """Smoke test: run the full pipeline with real API calls (text-only)."""
    graph = build_graph()
    state = initial_state(
        theme="A brief encounter at a train station",
        output_dir="/tmp/test_real_api",
        text_only=True,
        max_scenes=3,
        num_characters=2,
    )

    result = await graph.ainvoke(state)
    script = result["vn_script"]

    assert script is not None
    assert len(script.scenes) > 0
    assert any(line.text for scene in script.scenes for line in scene.dialogue)
