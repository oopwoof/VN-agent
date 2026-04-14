"""Tests for image_gen service (Sprint 6-9b): reference-image dispatch."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.services import image_gen


class _FakeSettings:
    def __init__(self, provider="openai", model="dall-e-3", google_key=""):
        self.image_provider = provider
        self.image_model = model
        self.openai_api_key = "sk-fake"
        self.stability_api_key = "sk-stab"
        self.google_api_key = google_key


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
    async def test_falls_back_to_text_when_no_ref_provider_has_creds(self, tmp_path):
        # Sprint 10-1 fallback chain: when the primary is non-ref and NO
        # ref-capable provider has credentials, silently degrade to
        # text-only via generate_image. (Previously: "unsupported primary"
        # always fell through; now we try the ref chain first.)
        out = tmp_path / "out.png"
        ref = tmp_path / "ref.png"
        ref.write_bytes(b"fake")
        settings = _FakeSettings("openai")
        settings.openai_api_key = ""     # kill gpt-image-1 credentials
        settings.stability_api_key = ""  # kill stability credentials
        settings.google_api_key = ""     # kill gemini credentials
        with patch("vn_agent.services.image_gen.get_settings", return_value=settings):
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


class TestGeminiProvider:
    """Sprint 10-1: Nano Banana (google_gemini) integration."""

    def test_gemini_supports_reference(self):
        with patch(
            "vn_agent.services.image_gen.get_settings",
            return_value=_FakeSettings("google_gemini", google_key="k"),
        ):
            assert image_gen.provider_supports_reference() is True

    @pytest.mark.asyncio
    async def test_gemini_routes_to_gemini_edit(self, tmp_path):
        out = tmp_path / "out.png"
        ref = tmp_path / "ref.png"
        ref.write_bytes(b"fake")
        settings = _FakeSettings("google_gemini", google_key="AIza-fake")
        with patch("vn_agent.services.image_gen.get_settings", return_value=settings):
            with patch(
                "vn_agent.services.image_gen._edit_gemini_with_reference",
                new=AsyncMock(return_value=out),
            ) as gem:
                await image_gen.generate_image_with_reference("prompt", ref, out)
                gem.assert_awaited_once_with("prompt", ref, out)

    @pytest.mark.asyncio
    async def test_gemini_falls_through_to_gpt_image_on_failure(self, tmp_path):
        """If Gemini 403s (free tier), chain walks to gpt-image-1."""
        out = tmp_path / "out.png"
        ref = tmp_path / "ref.png"
        ref.write_bytes(b"fake")
        settings = _FakeSettings("google_gemini", google_key="AIza-fake")
        with patch("vn_agent.services.image_gen.get_settings", return_value=settings):
            with patch(
                "vn_agent.services.image_gen._edit_gemini_with_reference",
                new=AsyncMock(side_effect=RuntimeError("simulated 403")),
            ):
                with patch(
                    "vn_agent.services.image_gen._edit_openai_gpt_image",
                    new=AsyncMock(return_value=out),
                ) as gpt:
                    result = await image_gen.generate_image_with_reference(
                        "prompt", ref, out,
                    )
                    assert result == out
                    gpt.assert_awaited_once()

    def test_extract_gemini_bytes_camelcase(self):
        resp = {
            "candidates": [{
                "content": {
                    "parts": [{"inlineData": {"data": "abc123"}}]
                }
            }]
        }
        assert image_gen._extract_gemini_image_bytes(resp) == "abc123"

    def test_extract_gemini_bytes_snakecase(self):
        resp = {
            "candidates": [{
                "content": {
                    "parts": [{"inline_data": {"data": "xyz"}}]
                }
            }]
        }
        assert image_gen._extract_gemini_image_bytes(resp) == "xyz"

    def test_extract_gemini_bytes_missing_raises(self):
        resp = {"candidates": [{"content": {"parts": [{"text": "no image"}]}}]}
        with pytest.raises(image_gen.ImageGenerationError):
            image_gen._extract_gemini_image_bytes(resp)
