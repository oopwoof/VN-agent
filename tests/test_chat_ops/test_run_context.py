"""Chat-ops image gating.

The suite forces mock mode globally, which is exactly why these live in
their own file: with mock on, every reason string reads "mock mode" and
the text-only branch would never be exercised. These flip the ContextVar
explicitly to check both reasons independently.
"""
from __future__ import annotations

from vn_agent.chat_ops.run_context import (
    images_allowed,
    no_images_reason,
    text_only_var,
)
from vn_agent.services.llm import mock_mode_var


def _with(mock: bool, text_only: bool):
    return mock_mode_var.set(mock), text_only_var.set(text_only)


def test_real_non_text_only_job_may_generate():
    m, t = _with(False, False)
    try:
        assert images_allowed() is True
    finally:
        text_only_var.reset(t)
        mock_mode_var.reset(m)


def test_text_only_job_may_not_generate_even_when_not_mock():
    """The pipeline honors text_only with a conditional edge past asset
    generation. A chat-ops turn runs after the pipeline and has no such
    edge, so without this check it would bill for an image the project
    was configured never to buy."""
    m, t = _with(False, True)
    try:
        assert images_allowed() is False
        assert "text-only" in no_images_reason()
    finally:
        text_only_var.reset(t)
        mock_mode_var.reset(m)


def test_mock_reason_wins_when_both_apply():
    m, t = _with(True, True)
    try:
        assert images_allowed() is False
        assert "mock" in no_images_reason()
    finally:
        text_only_var.reset(t)
        mock_mode_var.reset(m)


def test_default_is_not_text_only():
    """Defaulting to text_only would silently stop paid projects from
    generating the images they asked for."""
    assert text_only_var.get() is False
