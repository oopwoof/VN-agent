"""Pre-flight checks for real-API pipeline runs.

Catches common failure modes BEFORE the first expensive call:
  - Missing API keys for the providers we'll actually use
  - Unwritable output directory
  - Cost estimation users should see before spending money

Optional connectivity ping: a small probe call to verify each key is valid.
We default to off (offline, pure-config check) so CI and sandbox envs still
work; callers pass `ping=True` before real production runs.

This is imported only by CLI/demo scripts, not by the pipeline itself —
pipelines assume preflight has already run.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Cost model per image (USD) ──────────────────────────────────────────────
# Rough per-image prices at 1024×1024 standard quality. Update if Anthropic /
# OpenAI change pricing. Used only for estimates shown to the user.
_IMAGE_COST_PER_IMAGE = {
    "dall-e-3": 0.04,
    "dall-e-3-hd": 0.08,
    "gpt-image-1": 0.04,
    "gpt-image-1-medium": 0.04,
    "stability-sd3": 0.065,
    "stability-ultra": 0.08,
}


@dataclass
class PreflightReport:
    """Structured result of pre-flight checks."""
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cost_estimate_usd: float = 0.0
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    estimated_llm_calls: int = 0
    estimated_images: int = 0

    def format(self) -> str:
        lines: list[str] = []
        status = "✅ READY" if self.passed else "❌ NOT READY"
        lines.append(f"Pre-flight: {status}")
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in self.errors)
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {w}" for w in self.warnings)
        if self.cost_breakdown:
            lines.append("Cost estimate:")
            for label, amount in self.cost_breakdown.items():
                lines.append(f"  {label}: ${amount:.3f}")
            lines.append(f"  Total: ${self.cost_estimate_usd:.3f}")
        return "\n".join(lines)


def _llm_key_missing(settings) -> tuple[bool, str]:
    """Check LLM provider key presence. Returns (is_missing, key_label)."""
    # Explicit llm_api_key always wins (local model setup)
    if settings.llm_api_key:
        return False, "LLM_API_KEY"
    provider = settings.llm_provider
    if provider == "anthropic":
        present = bool(settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
        return not present, "ANTHROPIC_API_KEY"
    # openai or custom base_url
    present = bool(settings.openai_api_key or os.environ.get("OPENAI_API_KEY"))
    return not present, "OPENAI_API_KEY"


def _image_key_missing(settings) -> tuple[bool, str]:
    """Check image provider key. Returns (is_missing, key_label)."""
    provider = settings.image_provider
    if provider in {"openai", "openai_gpt_image", "dall-e-3", "gpt-image-1"}:
        present = bool(settings.openai_api_key or os.environ.get("OPENAI_API_KEY"))
        return not present, "OPENAI_API_KEY"
    if provider == "stability":
        present = bool(settings.stability_api_key or os.environ.get("STABILITY_API_KEY"))
        return not present, "STABILITY_API_KEY"
    # Unknown provider — warn but don't block
    return False, f"<unknown provider: {provider}>"


def estimate_cost(
    settings,
    max_scenes: int,
    num_characters: int,
    text_only: bool,
) -> tuple[float, dict[str, float], int, int]:
    """Back-of-envelope cost estimate for one full pipeline run.

    Intentionally conservative: uses median-case per-agent token budgets,
    not worst case. Returns (total_usd, breakdown_by_category,
    estimated_llm_calls, estimated_images).

    Token budgets chosen from historical trace.json samples on COLX_523
    runs — these are medians, not contracts. Real cost will vary ±30%.
    """
    # Median token budgets per LLM call (input, output). Re-calibrated
    # against real Sonnet 4.6 runs on 2026-04-13:
    #   director_step1:   in≈1400 out≈3700  (thinking blocks inflate output)
    #   director_step2:   in≈900  out≈7200  (entry_context + exit_hook + branches)
    #   writer (×6):      in≈1100 out≈3250  (max_dialogue_lines=20 usually filled)
    #   reviewer:        in≈5300 out≈1300  (reads FULL dialogue; model now
    #                    Sonnet per Sprint 7-3, rate auto-applied via
    #                    settings.llm_reviewer_model lookup below)
    # Previous values under-estimated total spend by ~3x.
    MEDIAN_TOK = {
        "director_step1": (1400, 3700),
        "director_step2": (900, 7200),
        "writer": (1100, 3250),            # per scene
        "reviewer": (5300, 1300),
        "character_designer": (500, 400),  # per character — unchanged, needs calibration
        "scene_artist": (500, 400),        # per unique background — unchanged
    }

    # Per-model rates $/M tokens (input, output)
    RATES = {
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-haiku-4-5-20251001": (0.80, 4.0),
        "gpt-4o": (2.5, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
    }

    def cost_call(model: str, tok_in: int, tok_out: int) -> float:
        rin, rout = RATES.get(model, (3.0, 15.0))  # default to Sonnet pricing
        return (tok_in * rin + tok_out * rout) / 1_000_000

    llm_cost = 0.0
    llm_calls = 0

    # Director: 2 calls
    for key in ("director_step1", "director_step2"):
        tok_in, tok_out = MEDIAN_TOK[key]
        llm_cost += cost_call(settings.llm_director_model, tok_in, tok_out)
        llm_calls += 1

    # Writer: one call per scene
    tok_in, tok_out = MEDIAN_TOK["writer"]
    llm_cost += max_scenes * cost_call(settings.llm_writer_model, tok_in, tok_out)
    llm_calls += max_scenes

    # Reviewer: 1 call (structural is pure code)
    tok_in, tok_out = MEDIAN_TOK["reviewer"]
    llm_cost += cost_call(settings.llm_reviewer_model, tok_in, tok_out)
    llm_calls += 1

    # Character designer + scene artist (skipped in text_only)
    if not text_only:
        tok_in, tok_out = MEDIAN_TOK["character_designer"]
        llm_cost += num_characters * cost_call(
            settings.llm_character_designer_model, tok_in, tok_out,
        )
        llm_calls += num_characters
        tok_in, tok_out = MEDIAN_TOK["scene_artist"]
        # Assume unique backgrounds ≈ max_scenes (worst case — could be less)
        llm_cost += max_scenes * cost_call(
            settings.llm_scene_artist_model, tok_in, tok_out,
        )
        llm_calls += max_scenes

    # Image generation cost
    image_cost = 0.0
    image_count = 0
    if not text_only:
        per_image = _IMAGE_COST_PER_IMAGE.get(settings.image_model, 0.04)
        # 3 emotions per character + 1 background per unique scene
        image_count = num_characters * 3 + max_scenes
        image_cost = image_count * per_image

    total = llm_cost + image_cost
    breakdown: dict[str, float] = {"LLM": round(llm_cost, 4)}
    if image_cost > 0:
        breakdown["Images"] = round(image_cost, 4)

    return round(total, 4), breakdown, llm_calls, image_count


async def check_readiness(
    settings,
    max_scenes: int,
    num_characters: int,
    text_only: bool,
    output_dir: Path | None = None,
    ping: bool = False,
) -> PreflightReport:
    """Run all pre-flight checks and return a structured report.

    Args:
        settings: Settings instance (from get_settings())
        max_scenes, num_characters, text_only: pipeline config for estimation
        output_dir: optional; if given, verified writable
        ping: if True, perform a small real API probe call per provider
              (costs ≤$0.001). Disabled by default to keep dry-run truly dry.
    """
    report = PreflightReport(passed=True)

    # ── Key checks ──────────────────────────────────────────────────────────
    missing, label = _llm_key_missing(settings)
    if missing:
        report.errors.append(f"{label} is not set (required for LLM provider '{settings.llm_provider}')")
        report.passed = False

    if not text_only:
        missing, label = _image_key_missing(settings)
        if missing:
            report.errors.append(f"{label} is not set (required for image provider '{settings.image_provider}')")
            report.passed = False

    # ── Output directory ────────────────────────────────────────────────────
    if output_dir is not None:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            probe = output_dir / ".preflight_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as e:
            report.errors.append(f"Output directory not writable: {output_dir} ({e})")
            report.passed = False

    # ── Cost estimate ───────────────────────────────────────────────────────
    total, breakdown, llm_calls, images = estimate_cost(
        settings, max_scenes, num_characters, text_only,
    )
    report.cost_estimate_usd = total
    report.cost_breakdown = breakdown
    report.estimated_llm_calls = llm_calls
    report.estimated_images = images

    # ── Optional connectivity ping ─────────────────────────────────────────
    if ping and report.passed:
        ping_error = await _ping_providers(settings, text_only)
        if ping_error:
            report.warnings.append(ping_error)

    return report


async def _ping_providers(settings, text_only: bool) -> str | None:
    """Minimal probe calls to verify credentials. Returns error string or None.

    Deliberately cheap: 1-token LLM completion, and a list-models call for
    the image API (no image generated). Total cost per ping ≤ $0.001.
    """
    try:
        from vn_agent.services.llm import ainvoke_llm

        await ainvoke_llm(
            "You answer in one word.", "Reply: ok",
            model=settings.llm_reviewer_model, caller="preflight/ping",
        )
    except Exception as e:
        return f"LLM ping failed: {e}"

    if not text_only:
        # Image API probe is a quick model-list GET, no generation. If the
        # user's image_provider doesn't expose such an endpoint we skip
        # quietly (most providers let a bogus call 401 cheaply anyway).
        try:
            import httpx

            if settings.image_provider in {"openai", "openai_gpt_image", "dall-e-3", "gpt-image-1"}:
                key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
                if key:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(
                            "https://api.openai.com/v1/models",
                            headers={"Authorization": f"Bearer {key}"},
                        )
                        if resp.status_code >= 400:
                            return f"Image API ping failed: HTTP {resp.status_code}"
        except Exception as e:
            return f"Image API ping error: {e}"

    return None
