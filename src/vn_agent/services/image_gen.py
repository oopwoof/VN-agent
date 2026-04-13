"""Image generation service (DALL-E 3 / Stability AI / gpt-image-1).

Supports two generation modes:
  - generate_image(prompt, output) → pure text-to-image (all providers)
  - generate_image_with_reference(prompt, reference, output) →
    image-to-image for character consistency across emotions

Provider capabilities:
  openai (DALL-E 3) — text only, no reference
  openai_gpt_image (gpt-image-1) — text + reference via /v1/images/edits
  stability (SDXL) — text + reference via init_image

Character consistency strategy: Sprint 6-9b generates neutral sprite
first as a visual anchor, then happy/sad as reference-based variants.
This is 10× more consistent than 3 independent text-to-image calls
because the LLM-provided "appearance" description can't capture enough
visual detail for DALL-E 3 to reproduce identically.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from vn_agent.config import get_settings

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    pass


# Providers that support reference-image conditioning
_PROVIDERS_WITH_REFERENCE = {"openai_gpt_image", "stability"}


def provider_supports_reference(provider: str | None = None) -> bool:
    """Check if the current or given image provider can accept a reference image."""
    if provider is None:
        provider = get_settings().image_provider
    return provider in _PROVIDERS_WITH_REFERENCE


async def generate_image(prompt: str, output_path: Path) -> Path:
    """Generate an image from prompt and save to output_path."""
    settings = get_settings()
    provider = settings.image_provider
    if provider in {"openai", "openai_gpt_image"}:
        return await _generate_openai(prompt, output_path)
    if provider == "stability":
        return await _generate_stability(prompt, output_path)
    # Unknown provider — try DALL-E as a sensible default
    logger.warning(f"Unknown image_provider '{provider}', defaulting to DALL-E")
    return await _generate_openai(prompt, output_path)


async def generate_image_with_reference(
    prompt: str, reference_path: Path, output_path: Path,
) -> Path:
    """Generate an image using a reference image for visual consistency.

    Used by CharacterDesigner to produce emotion variants (happy/sad) that
    share the neutral sprite's face, outfit, and art style.

    Falls back to pure text-to-image if the configured provider doesn't
    support reference images — the caller should ideally detect this via
    provider_supports_reference() first and enrich the prompt accordingly.
    """
    settings = get_settings()
    provider = settings.image_provider

    if not reference_path.exists():
        logger.warning(
            f"Reference {reference_path} missing — falling back to text-to-image"
        )
        return await generate_image(prompt, output_path)

    if provider == "openai_gpt_image":
        return await _edit_openai_gpt_image(prompt, reference_path, output_path)
    if provider == "stability":
        return await _img2img_stability(prompt, reference_path, output_path)

    # Provider doesn't support reference → degrade gracefully
    logger.info(
        f"Provider '{provider}' doesn't support reference images — "
        f"generating from prompt only (consistency may drift)"
    )
    return await generate_image(prompt, output_path)


async def _generate_openai(prompt: str, output_path: Path) -> Path:
    """Text-to-image via OpenAI (DALL-E 3 or gpt-image-1)."""
    settings = get_settings()
    url = "https://api.openai.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": settings.image_model,
        "prompt": prompt,
        "size": "1024x1024",
        "n": 1,
    }
    # DALL-E 3 supports quality + response_format; gpt-image-1 returns b64_json
    if settings.image_model.startswith("dall-e"):
        payload["quality"] = "standard"
        payload["response_format"] = "url"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()["data"][0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if "b64_json" in data:
            output_path.write_bytes(base64.b64decode(data["b64_json"]))
        elif "url" in data:
            img_resp = await client.get(data["url"])
            img_resp.raise_for_status()
            output_path.write_bytes(img_resp.content)
        else:
            raise ImageGenerationError(f"OpenAI response missing image data: {data.keys()}")
    logger.info(f"Generated image (text): {output_path}")
    return output_path


async def _edit_openai_gpt_image(
    prompt: str, reference_path: Path, output_path: Path,
) -> Path:
    """Image-to-image via OpenAI /v1/images/edits with gpt-image-1.

    Uses the reference image as a visual anchor so the result preserves
    the subject's features while the prompt describes the variation
    (e.g. same character, happy expression).
    """
    settings = get_settings()
    url = "https://api.openai.com/v1/images/edits"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    # multipart/form-data: image as PNG bytes + text fields
    with open(reference_path, "rb") as f:
        image_bytes = f.read()
    files = {"image": ("reference.png", image_bytes, "image/png")}
    data = {
        "model": settings.image_model or "gpt-image-1",
        "prompt": prompt,
        "size": "1024x1024",
        "n": "1",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, files=files, data=data)
        resp.raise_for_status()
        payload = resp.json()["data"][0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if "b64_json" in payload:
            output_path.write_bytes(base64.b64decode(payload["b64_json"]))
        elif "url" in payload:
            img_resp = await client.get(payload["url"])
            img_resp.raise_for_status()
            output_path.write_bytes(img_resp.content)
        else:
            raise ImageGenerationError(f"OpenAI edits response missing image: {payload.keys()}")
    logger.info(f"Generated image (reference): {output_path} ← {reference_path.name}")
    return output_path


async def _generate_stability(prompt: str, output_path: Path) -> Path:
    settings = get_settings()
    url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
    headers = {
        "Authorization": f"Bearer {settings.stability_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "text_prompts": [{"text": prompt, "weight": 1.0}],
        "cfg_scale": 7,
        "height": 1024,
        "width": 1024,
        "steps": 30,
        "samples": 1,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        image_data = resp.json()["artifacts"][0]["base64"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(image_data))
    logger.info(f"Generated image (text): {output_path}")
    return output_path


async def _img2img_stability(
    prompt: str, reference_path: Path, output_path: Path,
) -> Path:
    """Image-to-image via Stability SDXL with an init_image."""
    settings = get_settings()
    url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/image-to-image"
    headers = {
        "Authorization": f"Bearer {settings.stability_api_key}",
        "Accept": "application/json",
    }
    with open(reference_path, "rb") as f:
        init_image = f.read()
    files = {"init_image": ("reference.png", init_image, "image/png")}
    data = {
        "text_prompts[0][text]": prompt,
        "text_prompts[0][weight]": "1.0",
        "cfg_scale": "7",
        "steps": "30",
        "samples": "1",
        "init_image_mode": "IMAGE_STRENGTH",
        # How much of the reference to preserve (0=identical, 1=ignore).
        # 0.35 keeps face/outfit, lets emotion/pose vary.
        "image_strength": "0.35",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, files=files, data=data)
        resp.raise_for_status()
        image_data = resp.json()["artifacts"][0]["base64"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(image_data))
    logger.info(f"Generated image (reference): {output_path} ← {reference_path.name}")
    return output_path
