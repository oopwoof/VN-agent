"""Sprint 10-1: probe whether GOOGLE_API_KEY can hit Gemini.

Calls the FREE-tier Gemini 1.5 Flash text endpoint first (any paid or
free account can use it) so we confirm the key is valid before the
image-gen path (which requires paid tier) spends credits. If the text
probe passes but image gen fails later, that's almost certainly a
billing/tier issue, not a bad key.

Usage:
  uv run python scripts/check_gemini_access.py

Exit codes:
  0 — key works for text; image-gen may or may not work depending on tier
  1 — key unset or text probe failed
  2 — text works, image probe failed (free tier likely, or outage)
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vn_agent.config import get_settings  # noqa: E402


TEXT_MODEL = "gemini-1.5-flash"
IMAGE_MODEL = "gemini-2.5-flash-image-preview"
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


async def probe_text(api_key: str) -> tuple[bool, str]:
    """Free-tier text probe. Returns (success, message)."""
    url = f"{BASE}/{TEXT_MODEL}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": "Reply with one word: OK"}]}]}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload)
    if resp.status_code == 200:
        # Look for text in response
        try:
            content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return True, f"text probe OK: {content.strip()[:40]!r}"
        except (KeyError, IndexError):
            return False, f"text probe returned 200 but unexpected shape: {resp.text[:200]}"
    return False, f"text probe failed: HTTP {resp.status_code} — {resp.text[:200]}"


async def probe_image(api_key: str) -> tuple[bool, str]:
    """Image-gen probe. Spends credits if paid. Returns (success, message)."""
    url = f"{BASE}/{IMAGE_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "A single red dot on white."}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)
    if resp.status_code == 200:
        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            has_img = any(
                (p.get("inlineData") or p.get("inline_data")) for p in parts
            )
            if has_img:
                return True, "image probe OK (paid tier active)"
            return False, f"image 200 but no inline image part: {str(parts)[:200]}"
        except (KeyError, IndexError):
            return False, f"image 200 but unexpected shape: {resp.text[:200]}"
    if resp.status_code == 403:
        return False, (
            "image 403 — key valid for text but NO image-gen access. "
            "Likely cause: Gemini image generation requires a paid-tier "
            "(billing-enabled) project. Upgrade at console.cloud.google.com "
            "and retry."
        )
    if resp.status_code == 429:
        return False, "image 429 — rate limited (may also indicate free tier)"
    return False, f"image probe failed: HTTP {resp.status_code} — {resp.text[:200]}"


async def main() -> int:
    settings = get_settings()
    key = settings.google_api_key or os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        print("[FAIL] GOOGLE_API_KEY not set in .env or environment")
        return 1

    print(f"[info] using key ending in ...{key[-6:]}")

    # Text first (free)
    ok, msg = await probe_text(key)
    if not ok:
        print(f"[FAIL] {msg}")
        return 1
    print(f"[OK]   {msg}")

    # Image (paid-tier gated)
    ok, msg = await probe_image(key)
    if ok:
        print(f"[OK]   {msg}")
        print("")
        print("Image-gen is live. Nano Banana can serve Sprint 10-1 sprites.")
        return 0
    print(f"[WARN] {msg}")
    print("")
    print(
        "Text works but image-gen is not available on this account. "
        "The pipeline's fallback chain will route image calls to "
        "gpt-image-1 / DALL-E 3 automatically, so Phase 12 generation "
        "still works — just without Nano Banana's multi-ref consistency. "
        "Upgrade to paid Gemini when ready; no code change needed."
    )
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
