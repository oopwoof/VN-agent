"""Image generation service (Nano Banana / gpt-image-1 / DALL-E 3 / Stability).

Supports two generation modes:
  - generate_image(prompt, output) → pure text-to-image (all providers)
  - generate_image_with_reference(prompt, reference, output) →
    image-to-image for character consistency across emotions

Provider capabilities:
  google_gemini (Nano Banana, gemini-2.5-flash-image) — text + reference,
    multi-image ref supported natively (best for VN character consistency)
  openai_gpt_image (gpt-image-1) — text + reference via /v1/images/edits
  stability (SDXL) — text + reference via init_image
  openai (DALL-E 3) — text only, no reference

Sprint 10-1: Nano Banana added as preferred provider. Fallback chain on
4xx/5xx: google_gemini → openai_gpt_image → openai (DALL-E 3) → stability.
Config `image_provider` chooses the primary.

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
_PROVIDERS_WITH_REFERENCE = {"google_gemini", "openai_gpt_image", "stability"}

# Fallback chain for text-to-image (Sprint 10-1).
# When the primary provider hits a 4xx/5xx we walk down this list.
_TEXT_FALLBACK_CHAIN = ["google_gemini", "openai_gpt_image", "openai", "stability"]

# Fallback chain for reference-conditioned gen — only reference-capable
# providers; others would silently discard the reference image.
_REF_FALLBACK_CHAIN = ["google_gemini", "openai_gpt_image", "stability"]


def provider_supports_reference(provider: str | None = None) -> bool:
    """Check if the current or given image provider can accept a reference image."""
    if provider is None:
        provider = get_settings().image_provider
    return provider in _PROVIDERS_WITH_REFERENCE


async def _dispatch_text(
    provider: str, prompt: str, output_path: Path,
    aspect_ratio: str | None = None,
) -> Path:
    """Dispatch a text-to-image call to the right backend.

    aspect_ratio is provider-hinted (Nano Banana uses it directly; DALL-E /
    Stability map to nearest supported size, others ignore). Allowed values
    for Gemini: "1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2".
    """
    if provider == "google_gemini":
        return await _generate_gemini_image(prompt, output_path, aspect_ratio)
    if provider in {"openai", "openai_gpt_image"}:
        return await _generate_openai(prompt, output_path)
    if provider == "stability":
        return await _generate_stability(prompt, output_path)
    raise ImageGenerationError(f"Unknown text provider: {provider}")


async def _dispatch_ref(
    provider: str, prompt: str, reference_path: Path, output_path: Path,
    aspect_ratio: str | None = None,
) -> Path:
    """Dispatch a reference-conditioned call to the right backend."""
    if provider == "google_gemini":
        return await _edit_gemini_with_reference(
            prompt, reference_path, output_path, aspect_ratio,
        )
    if provider == "openai_gpt_image":
        return await _edit_openai_gpt_image(prompt, reference_path, output_path)
    if provider == "stability":
        return await _img2img_stability(prompt, reference_path, output_path)
    raise ImageGenerationError(f"Provider {provider} doesn't support reference")


async def generate_image(
    prompt: str, output_path: Path, aspect_ratio: str | None = None,
) -> Path:
    """Text-to-image with provider fallback chain.

    Tries the configured primary provider first; on failure walks down
    _TEXT_FALLBACK_CHAIN. This lets a paid-Gemini setup keep working
    even if Nano Banana rate-limits, and lets a free-tier Gemini user
    degrade to DALL-E transparently.

    aspect_ratio (Sprint 12-3c): forwarded to provider where supported.
    Use "16:9" for scene backgrounds (matches Ren'Py's 1920x1080 base)
    and "3:4" for character sprites (traditional VN full-body framing).
    None → provider default (usually 1:1).
    """
    settings = get_settings()
    primary = settings.image_provider

    # Primary first, then rest of chain (dedup to keep order stable)
    chain = [primary] + [p for p in _TEXT_FALLBACK_CHAIN if p != primary]
    last_error: Exception | None = None
    for provider in chain:
        if not _provider_has_credentials(provider, settings):
            continue
        try:
            return await _dispatch_text(provider, prompt, output_path, aspect_ratio)
        except Exception as e:
            if not _is_retryable_image_error(e):
                # Policy violation / auth / bad request — don't burn
                # other providers on the same doomed prompt.
                raise
            last_error = e
            logger.warning(
                f"Image provider '{provider}' failed ({type(e).__name__}: "
                f"{str(e)[:100]}), trying next in chain"
            )
    raise ImageGenerationError(
        f"All image providers in fallback chain failed. Last error: {last_error}"
    )


async def generate_image_with_reference(
    prompt: str, reference_path: Path, output_path: Path,
    aspect_ratio: str | None = None,
) -> Path:
    """Generate with reference image + provider fallback chain.

    When no configured ref-capable provider has credentials, silently
    degrades to text-only via generate_image — caller should have called
    provider_supports_reference() first to enrich the prompt if needed.
    """
    settings = get_settings()
    if not reference_path.exists():
        logger.warning(
            f"Reference {reference_path} missing — falling back to text-to-image"
        )
        return await generate_image(prompt, output_path, aspect_ratio)

    primary = settings.image_provider
    chain = [primary] + [p for p in _REF_FALLBACK_CHAIN if p != primary]
    last_error: Exception | None = None
    tried_any = False
    for provider in chain:
        if not provider_supports_reference(provider):
            continue
        if not _provider_has_credentials(provider, settings):
            continue
        tried_any = True
        try:
            return await _dispatch_ref(
                provider, prompt, reference_path, output_path, aspect_ratio,
            )
        except Exception as e:
            if not _is_retryable_image_error(e):
                raise
            last_error = e
            logger.warning(
                f"Ref-image provider '{provider}' failed "
                f"({type(e).__name__}: {str(e)[:100]}), trying next"
            )

    if not tried_any:
        logger.info(
            "No reference-capable provider has credentials — "
            "degrading to text-only (consistency may drift)"
        )
        return await generate_image(prompt, output_path, aspect_ratio)
    raise ImageGenerationError(
        f"All ref-capable providers failed. Last error: {last_error}"
    )


def _is_retryable_image_error(exc: Exception) -> bool:
    """Gemini-review fix: distinguish infrastructure failures (worth retrying
    against the next provider) from content/auth failures (same prompt will
    fail everywhere, fallback wastes money + risks safety-flag spirals).

    Retry on:
      - httpx.HTTPStatusError with 429 (rate limit) or 5xx (server-side)
      - httpx.TimeoutException / network errors
      - ImageGenerationError (our custom: malformed response, missing image)
    Do NOT retry on:
      - 400 (prompt policy violation / bad request)
      - 401 / 403 (auth / billing / tier not enabled)
      - 404 (model not found)
    """
    if isinstance(exc, ImageGenerationError):
        return True  # malformed response — next provider may work
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return True
        if 500 <= status < 600:
            return True
        # 400 / 401 / 403 / 404 / 422: not retryable
        return False
    # Generic network / transport
    if isinstance(exc, (httpx.RequestError, ConnectionError, TimeoutError)):
        return True
    # Unknown exception: play it safe and don't retry (avoids loops)
    return False


def _write_validated(output_path: Path, data: bytes) -> None:
    """Validate + write image bytes, ensuring parents exist."""
    _validate_image_bytes(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)


def _validate_image_bytes(data: bytes) -> None:
    """Gemini-review fix: verify decoded bytes look like a real image
    before writing to disk. Prevents a silent 0-byte file or malformed
    base64 from being served to Ren'Py as a valid sprite.
    """
    if not data or len(data) < 16:
        raise ImageGenerationError(
            f"Image payload too small: {len(data) if data else 0} bytes"
        )
    # Known magic numbers for formats the pipeline may receive
    magic_checks = (
        b"\x89PNG\r\n\x1a\n",  # PNG
        b"\xff\xd8\xff",       # JPEG
        b"GIF87a",
        b"GIF89a",
        b"RIFF",               # WebP (starts with RIFF...WEBP)
    )
    if not any(data.startswith(m) for m in magic_checks):
        raise ImageGenerationError(
            f"Decoded bytes don't match a known image format "
            f"(head: {data[:8]!r})"
        )


def _provider_has_credentials(provider: str, settings) -> bool:
    """Whether the given provider has the credentials it needs."""
    if provider == "google_gemini":
        return bool(settings.google_api_key)
    if provider in {"openai", "openai_gpt_image"}:
        return bool(settings.openai_api_key)
    if provider == "stability":
        return bool(settings.stability_api_key)
    return False


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
        if "b64_json" in data:
            _write_validated(output_path, base64.b64decode(data["b64_json"]))
        elif "url" in data:
            img_resp = await client.get(data["url"])
            img_resp.raise_for_status()
            _write_validated(output_path, img_resp.content)
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
        if "b64_json" in payload:
            _write_validated(output_path, base64.b64decode(payload["b64_json"]))
        elif "url" in payload:
            img_resp = await client.get(payload["url"])
            img_resp.raise_for_status()
            _write_validated(output_path, img_resp.content)
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
        _write_validated(output_path, base64.b64decode(image_data))
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
        _write_validated(output_path, base64.b64decode(image_data))
    logger.info(f"Generated image (reference): {output_path} ← {reference_path.name}")
    return output_path


# ── Google Gemini (Nano Banana) backend ──────────────────────────────────
# Gemini 2.5 Flash Image (aka "Nano Banana") generates images via the
# generateContent endpoint with response_modalities=["IMAGE"]. Reference-image
# editing works by including the reference as an inline_data part in the
# same request alongside the text prompt.
#
# Key property for VN character consistency: supports MULTIPLE reference
# images in one call — the Sprint 6-9b neutral-first strategy can anchor
# to neutral + prior-emotion together.
#
# Endpoint: POST to the v1beta API. Auth via ?key= query string.

# Available Gemini image models (2025-11 v1beta list, in quality order):
#   nano-banana-pro-preview          (branded Pro, top tier)
#   gemini-3.1-flash-image-preview   (latest preview)
#   gemini-3-pro-image-preview       (Pro preview)
#   gemini-2.5-flash-image           (stable default)
_GEMINI_IMAGE_DEFAULT = "gemini-2.5-flash-image"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _gemini_image_model() -> str:
    """Resolve which Gemini image model to use. Respects settings.image_model
    when it's a Gemini-family name; otherwise falls back to the stable
    gemini-2.5-flash-image. Lets users opt into nano-banana-pro-preview
    or a future 3.x variant via config without code change.
    """
    settings = get_settings()
    m = (settings.image_model or "").strip()
    if m and ("gemini" in m.lower() or "nano-banana" in m.lower()):
        return m
    return _GEMINI_IMAGE_DEFAULT


async def _generate_gemini_image(
    prompt: str, output_path: Path, aspect_ratio: str | None = None,
) -> Path:
    """Text-to-image via Gemini 2.5 Flash Image."""
    settings = get_settings()
    if not settings.google_api_key:
        raise ImageGenerationError("GOOGLE_API_KEY not set")

    url = f"{_GEMINI_BASE}/{_gemini_image_model()}:generateContent?key={settings.google_api_key}"
    gen_config: dict = {"responseModalities": ["IMAGE"]}
    if aspect_ratio:
        # Gemini 2.5 Flash Image accepts aspectRatio in imageConfig.
        # Valid values: "1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2".
        gen_config["imageConfig"] = {"aspectRatio": aspect_ratio}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        image_b64 = _extract_gemini_image_bytes(resp.json())
        _write_validated(output_path, base64.b64decode(image_b64))
    logger.info(f"Generated image (gemini text): {output_path}")
    return output_path


async def _edit_gemini_with_reference(
    prompt: str, reference_path: Path, output_path: Path,
    aspect_ratio: str | None = None,
) -> Path:
    """Reference-conditioned gen via Gemini 2.5 Flash Image.

    The reference is sent as an inline_data part; the prompt instructs the
    model to preserve the subject's features. Multi-reference (neutral +
    prior emotion) is supported by adding more inline_data parts — we keep
    it single-reference here to match the existing sprite-gen signature.
    """
    settings = get_settings()
    if not settings.google_api_key:
        raise ImageGenerationError("GOOGLE_API_KEY not set")

    with open(reference_path, "rb") as f:
        ref_bytes = f.read()
    ref_b64 = base64.b64encode(ref_bytes).decode("ascii")

    url = f"{_GEMINI_BASE}/{_gemini_image_model()}:generateContent?key={settings.google_api_key}"
    gen_config: dict = {"responseModalities": ["IMAGE"]}
    if aspect_ratio:
        gen_config["imageConfig"] = {"aspectRatio": aspect_ratio}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": ref_b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": gen_config,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        image_b64 = _extract_gemini_image_bytes(resp.json())
        _write_validated(output_path, base64.b64decode(image_b64))
    logger.info(
        f"Generated image (gemini reference): {output_path} ← {reference_path.name}"
    )
    return output_path


def _extract_gemini_image_bytes(response_json: dict) -> str:
    """Pull the base64 image payload out of a Gemini generateContent response.

    Response shape:
      {candidates: [{content: {parts: [{inlineData: {data: "<b64>"}}, ...]}}]}
    """
    try:
        candidates = response_json["candidates"]
        parts = candidates[0]["content"]["parts"]
        for part in parts:
            # SDK may use camelCase OR snake_case depending on version
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return inline["data"]
    except (KeyError, IndexError, TypeError) as e:
        raise ImageGenerationError(
            f"Gemini response missing image data: {e}. "
            f"Response keys: {list(response_json.keys())}"
        ) from e
    raise ImageGenerationError("Gemini response had no inline image part")
