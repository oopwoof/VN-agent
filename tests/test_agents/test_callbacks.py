"""Tests for callback protocol."""
from vn_agent.agents.callbacks import noop_callback


def test_noop_callback():
    noop_callback("director", "planning story")  # should not raise
