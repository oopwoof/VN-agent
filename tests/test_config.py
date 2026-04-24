"""Tests for vn_agent.config.Settings cross-field validators.

Focus: Phase 13-2 Step 4b coupling rule between writer_max_concurrent
and the thinking pipeline flags. Sequential default must not require
anything; parallel path must fail fast if thinking is missing.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from vn_agent.config import Settings


class TestWriterConcurrencyCoupling:
    """writer_max_concurrent>1 requires thinking_fanout ON + consume ON."""

    def test_default_sequential_is_valid(self):
        """Default writer_max_concurrent=1 bypasses the coupling check."""
        s = Settings(writer_max_concurrent=1)
        assert s.writer_max_concurrent == 1
        assert s.enable_thinking_fanout is False
        assert s.writer_consume_thinking is False

    def test_parallel_with_full_thinking_stack_is_valid(self):
        """max_concurrent>1 + both thinking flags ON → accepted."""
        s = Settings(
            writer_max_concurrent=5,
            enable_thinking_fanout=True,
            writer_consume_thinking=True,
        )
        assert s.writer_max_concurrent == 5

    def test_parallel_without_thinking_fanout_rejected(self):
        """max_concurrent>1 without enable_thinking_fanout → ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                writer_max_concurrent=3,
                enable_thinking_fanout=False,
                writer_consume_thinking=True,
            )
        msg = str(exc_info.value)
        assert "writer_max_concurrent=3" in msg
        assert "enable_thinking_fanout" in msg

    def test_parallel_without_consume_rejected(self):
        """max_concurrent>1 without writer_consume_thinking → ValidationError.

        Thinking produced but not consumed = wasted money, no coordination
        signal reaches the Writer — same failure mode as no thinking at all.
        """
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                writer_max_concurrent=3,
                enable_thinking_fanout=True,
                writer_consume_thinking=False,
            )
        assert "writer_consume_thinking" in str(exc_info.value)

    def test_parallel_with_both_flags_off_lists_both_in_error(self):
        """Error message should enumerate every missing flag at once."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                writer_max_concurrent=5,
                enable_thinking_fanout=False,
                writer_consume_thinking=False,
            )
        msg = str(exc_info.value)
        assert "enable_thinking_fanout" in msg
        assert "writer_consume_thinking" in msg

    def test_sequential_with_thinking_flags_ignored(self):
        """max_concurrent=1 with thinking flags in either state is fine.

        Sequential path may or may not use thinking; coupling rule only
        kicks in when concurrent workers actually need the substitute signal.
        """
        s = Settings(
            writer_max_concurrent=1,
            enable_thinking_fanout=False,
            writer_consume_thinking=False,
        )
        assert s.writer_max_concurrent == 1
