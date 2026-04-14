"""Tests for prompt templates and utilities."""
from vn_agent.prompts.templates import (
    DIRECTOR_DETAILS_SYSTEM,
    DIRECTOR_OUTLINE_SYSTEM,
    REVIEWER_SYSTEM,
    WRITER_SYSTEM,
    strip_thinking,
)


class TestStripThinking:
    def test_removes_single_block(self):
        text = "before <thinking>some reasoning</thinking> after"
        assert strip_thinking(text) == "before  after"

    def test_removes_multiline_block(self):
        text = "intro\n<thinking>\nstep 1\nstep 2\n</thinking>\n{\"key\": \"value\"}"
        result = strip_thinking(text)
        assert "<thinking>" not in result
        assert '{"key": "value"}' in result

    def test_removes_multiple_blocks(self):
        text = "<thinking>a</thinking> middle <thinking>b</thinking> end"
        assert strip_thinking(text) == "middle  end"

    def test_no_thinking_unchanged(self):
        text = '{"title": "test"}'
        assert strip_thinking(text) == text

    def test_empty_string(self):
        assert strip_thinking("") == ""

    def test_nested_angle_brackets(self):
        text = "<thinking>if x > 0 and y < 10</thinking> result"
        assert strip_thinking(text) == "result"


class TestTemplateContent:
    def test_director_outline_has_planning_steps(self):
        assert "Step 1" in DIRECTOR_OUTLINE_SYSTEM
        assert "Step 4" in DIRECTOR_OUTLINE_SYSTEM
        assert "{strategies}" in DIRECTOR_OUTLINE_SYSTEM

    def test_director_details_has_thinking_guidance(self):
        assert "<thinking>" in DIRECTOR_DETAILS_SYSTEM
        assert "branch" in DIRECTOR_DETAILS_SYSTEM.lower()

    def test_writer_has_thinking_guidance(self):
        assert "<thinking>" in WRITER_SYSTEM
        assert "emotion" in WRITER_SYSTEM.lower()

    def test_reviewer_has_rubric(self):
        # Sprint 7-5b: rubric scoped to CRAFT dimensions only; structural
        # dimensions moved to StructureReviewer. Updated dimension names:
        # voice / subtext / arc / pacing / strategy_execution.
        assert "Character Voice" in REVIEWER_SYSTEM
        assert "Subtext" in REVIEWER_SYSTEM
        assert "Emotional Arc" in REVIEWER_SYSTEM
        assert "Pacing" in REVIEWER_SYSTEM
        assert "Strategy execution" in REVIEWER_SYSTEM
        assert "3.5" in REVIEWER_SYSTEM
