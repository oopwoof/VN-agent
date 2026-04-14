"""Tests for CharacterDesigner neutral-first sprite strategy (Sprint 6-9b)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.agents.character_designer import _generate_sprites
from vn_agent.schema.character import CharacterProfile, VisualProfile


def _make_char() -> CharacterProfile:
    return CharacterProfile(
        id="yui",
        name="Yui",
        personality="gentle",
        background="lighthouse keeper",
        role="protagonist",
    )


def _make_visual() -> VisualProfile:
    return VisualProfile(
        art_style="anime style",
        appearance="short brown hair, green eyes",
        default_outfit="wool sweater",
    )


async def _write_png(prompt: str, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"neutral-bytes")
    return output_path


async def _write_png_ref(prompt: str, reference_path: Path, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"variant-bytes")
    return output_path


@pytest.fixture(autouse=True)
def _disable_sprite_cutout(monkeypatch):
    """Sprint 12-3b: tests write fake PNG bytes, so rembg can't decode them.
    Disable the cutout pass so tests exercise the text/reference generation
    path only. Real-run behavior is covered by the live rembg smoke check.
    """
    from vn_agent.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "sprite_cutout", False, raising=False)


class TestNeutralFirstSprites:
    @pytest.mark.asyncio
    async def test_produces_three_sprites_in_order(self, tmp_path):
        char = _make_char()
        visual = _make_visual()
        with patch(
            "vn_agent.agents.character_designer.generate_image",
            new=AsyncMock(side_effect=_write_png),
        ), patch(
            "vn_agent.services.image_gen.provider_supports_reference",
            return_value=False,
        ):
            sprites, errors = await _generate_sprites(char, visual, str(tmp_path))

        assert [s.emotion for s in sprites] == ["neutral", "happy", "sad"]
        assert errors == []

    @pytest.mark.asyncio
    async def test_uses_reference_when_provider_supports_it(self, tmp_path):
        char = _make_char()
        visual = _make_visual()
        text_mock = AsyncMock(side_effect=_write_png)
        ref_mock = AsyncMock(side_effect=_write_png_ref)
        with patch(
            "vn_agent.agents.character_designer.generate_image", new=text_mock,
        ), patch(
            "vn_agent.services.image_gen.generate_image_with_reference", new=ref_mock,
        ), patch(
            "vn_agent.services.image_gen.provider_supports_reference",
            return_value=True,
        ):
            sprites, errors = await _generate_sprites(char, visual, str(tmp_path))

        # neutral = 1 text call, happy + sad = 2 reference calls
        assert text_mock.await_count == 1
        assert ref_mock.await_count == 2
        assert errors == []
        assert len(sprites) == 3

    @pytest.mark.asyncio
    async def test_text_only_reuses_same_base_descriptor(self, tmp_path):
        """When no reference available, all 3 prompts share visual descriptor."""
        char = _make_char()
        visual = _make_visual()
        captured: list[str] = []

        async def capture(prompt: str, output_path: Path):
            captured.append(prompt)
            return await _write_png(prompt, output_path)

        with patch(
            "vn_agent.agents.character_designer.generate_image",
            new=AsyncMock(side_effect=capture),
        ), patch(
            "vn_agent.services.image_gen.provider_supports_reference",
            return_value=False,
        ):
            await _generate_sprites(char, visual, str(tmp_path))

        assert len(captured) == 3
        # Every prompt must contain the full base descriptor for consistency
        for p in captured:
            assert "anime style" in p
            assert "short brown hair" in p
            assert "wool sweater" in p

    @pytest.mark.asyncio
    async def test_emotion_failure_falls_back_to_neutral_copy(self, tmp_path):
        char = _make_char()
        visual = _make_visual()

        async def flaky_ref(prompt, ref, out):
            raise RuntimeError("API down")

        with patch(
            "vn_agent.agents.character_designer.generate_image",
            new=AsyncMock(side_effect=_write_png),
        ), patch(
            "vn_agent.services.image_gen.generate_image_with_reference",
            new=AsyncMock(side_effect=flaky_ref),
        ), patch(
            "vn_agent.services.image_gen.provider_supports_reference",
            return_value=True,
        ):
            sprites, errors = await _generate_sprites(char, visual, str(tmp_path))

        # All 3 sprite metadata entries still present (no dangling Ren'Py refs)
        assert len(sprites) == 3
        assert len(errors) == 2  # happy + sad both failed
        # happy.png and sad.png should exist as copies of neutral bytes
        happy = tmp_path / "game" / "images" / "characters" / "yui" / "happy.png"
        sad = tmp_path / "game" / "images" / "characters" / "yui" / "sad.png"
        neutral = tmp_path / "game" / "images" / "characters" / "yui" / "neutral.png"
        assert happy.exists()
        assert sad.exists()
        assert happy.read_bytes() == neutral.read_bytes()
        assert sad.read_bytes() == neutral.read_bytes()

    @pytest.mark.asyncio
    async def test_neutral_failure_still_returns_metadata(self, tmp_path):
        """Even if neutral fails, sprite metadata is returned so Ren'Py refs exist."""
        char = _make_char()
        visual = _make_visual()

        async def always_fail(prompt, output_path):
            raise RuntimeError("down")

        with patch(
            "vn_agent.agents.character_designer.generate_image",
            new=AsyncMock(side_effect=always_fail),
        ), patch(
            "vn_agent.services.image_gen.provider_supports_reference",
            return_value=False,
        ):
            sprites, errors = await _generate_sprites(char, visual, str(tmp_path))

        assert [s.emotion for s in sprites] == ["neutral", "happy", "sad"]
        # 1 neutral + 2 emotions all failed
        assert len(errors) == 3
