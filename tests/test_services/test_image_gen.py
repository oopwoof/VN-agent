"""Tests for image_gen service (Sprint 6-9b): reference-image dispatch."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.services import image_gen


class _FakeSettings:
    def __init__(self, provider="openai", model="dall-e-3"):
        self.image_provider = provider
        self.image_model = model
        self.openai_api_key = "sk-fake"
        self.stability_api_key = "sk-stab"


class TestProviderSupportsReference:
    def test_dalle_does_not_support_reference(self):
        with patch("vn_agent.services.image_gen.get_settings", return_value=_FakeSettings("openai")):
            assert image_gen.provider_supports_reference() is False

    def test_gpt_image_supports_reference(self):
        with patch("vn_agent.services.image_gen.get_settings", return_value=_FakeSettings("openai_gpt_image")):
            assert image_gen.provider_supports_reference() is True

    def test_stability_supports_reference(self):
        with patch("vn_agent.services.image_gen.get_settings", return_value=_FakeSettings("stability")):
            assert image_gen.provider_supports_reference() is True

    def test_explicit_provider_arg_overrides(self):
        # Even with a non-ref provider in settings, explicit arg wins
        with patch("vn_agent.services.image_gen.get_settings", return_value=_FakeSettings("openai")):
            assert image_gen.provider_supports_reference("stability") is True
            assert image_gen.provider_supports_reference("openai") is False


class TestGenerateImageWithReferenceDispatch:
    @pytest.mark.asyncio
    async def test_missing_reference_falls_back_to_text(self, tmp_path):
        out = tmp_path / "out.png"
        missing_ref = tmp_path / "does_not_exist.png"
        with patch("vn_agent.services.image_gen.get_settings", return_value=_FakeSettings("openai_gpt_image")):
            with patch(
                "vn_agent.services.image_gen.generate_image",
                new=AsyncMock(return_value=out),
            ) as fallback:
                await image_gen.generate_image_with_reference("prompt", missing_ref, out)
                fallback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unsupported_provider_falls_back_to_text(self, tmp_path):
        out = tmp_path / "out.png"
        ref = tmp_path / "ref.png"
        ref.write_bytes(b"fake")
        with patch("vn_agent.services.image_gen.get_settings", return_value=_FakeSettings("openai")):
            with patch(
                "vn_agent.services.image_gen.generate_image",
                new=AsyncMock(return_value=out),
            ) as fallback:
                await image_gen.generate_image_with_reference("prompt", ref, out)
                fallback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gpt_image_routes_to_edit_endpoint(self, tmp_path):
        out = tmp_path / "out.png"
        ref = tmp_path / "ref.png"
        ref.write_bytes(b"fake")
        settings = _FakeSettings("openai_gpt_image", "gpt-image-1")
        with patch("vn_agent.services.image_gen.get_settings", return_value=settings):
            with patch(
                "vn_agent.services.image_gen._edit_openai_gpt_image",
                new=AsyncMock(return_value=out),
            ) as edit:
                await image_gen.generate_image_with_reference("prompt", ref, out)
                edit.assert_awaited_once_with("prompt", ref, out)

    @pytest.mark.asyncio
    async def test_stability_routes_to_img2img(self, tmp_path):
        out = tmp_path / "out.png"
        ref = tmp_path / "ref.png"
        ref.write_bytes(b"fake")
        with patch("vn_agent.services.image_gen.get_settings", return_value=_FakeSettings("stability")):
            with patch(
                "vn_agent.services.image_gen._img2img_stability",
                new=AsyncMock(return_value=out),
            ) as img2img:
                await image_gen.generate_image_with_reference("prompt", ref, out)
                img2img.assert_awaited_once_with("prompt", ref, out)
