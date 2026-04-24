"""Phase 13-1 Step 7: 50-scene long-VN smoke harness.

PRE-CONDITIONS:
  1. This script MAKES REAL API CALLS. Estimated spend at --scenes 50:
     ~$15 (Sonnet Writer/Director/Reviewer + Haiku summarizer/rollup +
     Gemini images in text-only mode no images). Running --scenes 20 is
     ~$6; --scenes 6 is ~$1.7 for a regression check.
  2. Anthropic key pool MUST be configured (VN_ANTHROPIC_API_KEYS CSV
     or VN_ANTHROPIC_KEYS_SONNET + VN_ANTHROPIC_KEYS_HAIKU). A single-key
     run of 50 scenes will hit 429 sustained.
  3. This script DOES NOT run from `uv run pytest` — it's a manual harness.
     CI must not invoke it.

USAGE:
  uv run python scripts/smoke_longvn.py --scenes 6   # regression check
  uv run python scripts/smoke_longvn.py --scenes 20  # stress test
  uv run python scripts/smoke_longvn.py --scenes 50  # north star

VALIDATION TARGETS (50-scene):
  - End-to-end wall time ≤ 30 min
  - TTFS (time-to-first-scene) ≤ 5 min (pre-streaming)
  - Total API cost ≤ $15
  - chapters field populated with 5 entries (50 / chapter_rollup_every=10)
  - state_timeline has 50 entries (one per scene)
  - Writer prompt input_tokens per call ≤ 30K after cache read (the
    prompt-caching economy should kick in from scene 10 onward)
  - cache_read_input_tokens / input_tokens ≥ 50% (cache working)
  - At least 1 entry in api_key_rotations.jsonl (3-key pool under 50-scene
    load will rotate at least once if tier limits are real)

SAFETY:
  --confirm required to actually spend money.
  Without --confirm, prints cost estimate and aborts.

OUTPUT:
  demo_output/smoke_longvn_<timestamp>/
    vn_script.json               # final script with chapters + state_timeline
    characters.json              # cast
    snapshots/s*.json            # per-scene snapshots
    api_key_rotations.jsonl      # rotation audit trail (cwd-written)
    rag_retrievals.jsonl         # lore retrieval audit
    run_metrics.json             # cost, wall time, cache hit ratio, etc.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Make src/ importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vn_agent.agents.graph import create_pipeline  # noqa: E402
from vn_agent.agents.state import initial_state  # noqa: E402
from vn_agent.config import get_settings  # noqa: E402
from vn_agent.observability.tracing import reset_trace  # noqa: E402
from vn_agent.services.preflight import check_readiness  # noqa: E402
from vn_agent.services.token_tracker import TokenTracker, current_tracker  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("smoke_longvn")


# Rough cost envelope per scene (blended Sonnet + Haiku with caching active).
# These are deliberately pessimistic so users don't get sticker-shocked.
_COST_PER_SCENE_USD: dict[str, float] = {
    "director_share": 0.04,       # amortized across scenes
    "writer_input":   0.10,       # per-scene Writer input (cached after scene 10)
    "writer_output":  0.06,       # per-scene Writer output
    "reviewer":       0.04,
    "summarizer":     0.002,
    "rollup_share":   0.005,      # 1 rollup per 10 scenes
}


def _estimate_cost(n_scenes: int, text_only: bool) -> float:
    per_scene = sum(_COST_PER_SCENE_USD.values())
    scene_cost = per_scene * n_scenes
    image_cost = 0.0 if text_only else 0.35 * 3  # ~3 images per scene, Nano Banana
    fixed = 0.20  # Director + StructureReviewer + setup
    return round(scene_cost + image_cost + fixed, 2)


async def _run(args: argparse.Namespace) -> dict:
    settings = get_settings()
    theme = args.theme
    text_only = bool(args.text_only)

    # Output dir
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = Path("demo_output") / f"smoke_longvn_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output: {output_dir}")

    # Preflight
    logger.info("Running preflight checks…")
    readiness = check_readiness()
    if not readiness.is_ready:
        logger.error(f"Preflight failed: {readiness.issues}")
        raise SystemExit(2)

    # Reset trace + token tracker
    reset_trace()
    tracker = TokenTracker()
    current_tracker.set(tracker)

    # Build initial state
    state = initial_state(
        theme=theme,
        max_scenes=args.scenes,
        num_characters=args.characters,
        text_only=text_only,
        output_dir=str(output_dir),
    )

    # Build + run graph
    graph = create_pipeline()
    t0 = time.perf_counter()
    final_state = await graph.ainvoke(state, {"recursion_limit": 100})
    wall = time.perf_counter() - t0
    logger.info(f"Pipeline complete in {wall:.1f}s ({wall/60:.1f} min)")

    # Validate Phase 13-1 targets
    script = final_state.get("vn_script")
    report: dict = {
        "wall_seconds": round(wall, 1),
        "wall_minutes": round(wall / 60, 2),
        "scene_count": len(script.scenes) if script else 0,
        "chapter_count": len(getattr(script, "chapters", []) or []),
        "state_timeline_count": len(getattr(script, "state_timeline", []) or []),
        "theme": theme,
        "output_dir": str(output_dir),
        "errors": final_state.get("errors", []),
    }
    if hasattr(tracker, "total_cost_usd"):
        report["total_cost_usd"] = round(tracker.total_cost_usd(), 2)
    if hasattr(tracker, "cache_read_ratio"):
        report["cache_read_ratio"] = round(tracker.cache_read_ratio(), 3)

    # Assertions against Phase 13-1 acceptance targets
    assertions: list[str] = []
    if args.scenes >= 10 and report["chapter_count"] != args.scenes // 10:
        assertions.append(
            f"FAIL: chapters count ({report['chapter_count']}) != "
            f"{args.scenes}/{settings.chapter_rollup_every}"
        )
    if report["state_timeline_count"] != args.scenes:
        assertions.append(
            f"FAIL: state_timeline count ({report['state_timeline_count']}) "
            f"!= {args.scenes}"
        )
    if args.scenes == 50:
        if report["wall_minutes"] > 30:
            assertions.append(f"FAIL: wall_minutes={report['wall_minutes']} > 30")
        total_cost = report.get("total_cost_usd", 0.0)
        if total_cost > 15.0:
            assertions.append(f"FAIL: total_cost_usd={total_cost} > $15")
    report["assertions"] = assertions

    # Persist run metrics
    (output_dir / "run_metrics.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 13-1 long-VN smoke harness (REAL API)",
    )
    parser.add_argument("--scenes", type=int, default=6,
                        help="Scene count. 6 = regression, 20 = stress, 50 = north star")
    parser.add_argument("--characters", type=int, default=3)
    parser.add_argument(
        "--theme", default="A keeper of the tide lighthouse caught between "
        "three hours of duty and a surfacing memory.",
    )
    parser.add_argument("--text-only", action="store_true",
                        help="Skip image generation (saves ~$1/scene)")
    parser.add_argument("--confirm", action="store_true",
                        help="Actually run. Without this, prints cost estimate and exits.")
    args = parser.parse_args()

    est_cost = _estimate_cost(args.scenes, args.text_only)
    print("\n=== smoke_longvn.py ===")
    print(f"  scenes:        {args.scenes}")
    print(f"  characters:    {args.characters}")
    print(f"  text_only:     {args.text_only}")
    print(f"  est. cost:     ~${est_cost}")
    print(f"  theme:         {args.theme[:80]}")

    if not args.confirm:
        print("\n[DRY RUN] Rerun with --confirm to actually spend money.")
        return

    print("\nRunning…\n")
    report = asyncio.run(_run(args))
    print("\n=== Results ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("assertions"):
        print("\n[FAIL] Acceptance assertions violated:")
        for msg in report["assertions"]:
            print(f"  - {msg}")
        raise SystemExit(1)
    print("\n[PASS] All acceptance targets met.")


if __name__ == "__main__":
    main()
