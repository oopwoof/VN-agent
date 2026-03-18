"""Image generation service (DALL-E 3 / Stability AI)."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from vn_agent.config import get_settings

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    pass


async def generate_image(prompt: str, output_path: Path) -> Path:
    """Generate an image from prompt and save to output_path."""
    settings = get_settings()
    if settings.image_provider == "openai":
        return await _generate_dalle(prompt, output_path)
    else:
        return await _generate_stability(prompt, output_path)


async def _generate_dalle(prompt: str, output_path: Path) -> Path:
    settings = get_settings()
    url = "https://api.openai.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.image_model,
        "prompt": prompt,
        "size": "1024x1024",
        "quality": "standard",
        "response_format": "url",
        "n": 1,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        image_url = resp.json()["data"][0]["url"]
        img_resp = await client.get(image_url)
        img_resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(img_resp.content)
    logger.info(f"Generated image: {output_path}")
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
        import base64
        image_data = resp.json()["artifacts"][0]["base64"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(image_data))
    logger.info(f"Generated image: {output_path}")
    return output_path
