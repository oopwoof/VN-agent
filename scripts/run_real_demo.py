"""Real end-to-end demo runner — Sprint 6-9c.

Runs the full VN-Agent pipeline against real APIs (Sonnet + gpt-image-1)
and captures a reviewable artifact under demo_output/vn_<timestamp>/.

Guardrails:
  1. Always calls preflight FIRST. If it fails, we exit before any spend.
  2. Always shows the estimated cost breakdown.
  3. Unless --confirm is passed, prompts interactively; typing anything
     other than "y" aborts.
  4. Writes run metadata (cost, timing, errors) next to the Ren'Py
     project so you can reconstruct what happened without re-running.

Typical usage:
  # dry run — cost estimate only, no spend
  uv run python scripts/run_real_demo.py --theme "A lighthouse keeper during a storm"

  # actually spend (~$0.30–0.50)
  uv run python scripts/run_real_demo.py \\
      --theme "A lighthouse keeper during a storm" --confirm
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Make src/ importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vn_agent.agents.graph import create_pipeline  # noqa: E402
from vn_agent.agents.state import initial_state  # noqa: E402
from vn_agent.compiler.project_builder import build_project  # noqa: E402
from vn_agent.config import get_settings  # noqa: E402
from vn_agent.observability.tracing import reset_trace  # noqa: E402
from vn_agent.services.preflight import check_readiness  # noqa: E402
from vn_agent.services.token_tracker import TokenTracker, current_tracker  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("real_demo")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--theme", required=True, help="Story premise")
    p.add_argument("--max-scenes", type=int, default=6, help="Upper bound on scene count (default: 6 for cheap demos)")
    p.add_argument("--characters", type=int, default=3, help="Target number of characters")
    p.add_argument("--text-only", action="store_true", help="Skip images/music (cheap sanity-check run)")
    p.add_argument(
        "--confirm", action="store_true",
        help="Skip the interactive y/n prompt. Use only when you've already reviewed the cost estimate.",
    )
    p.add_argument(
        "--output-root", type=Path, default=Path("demo_output"),
        help="Parent directory for the timestamped run (default: demo_output)",
    )
    p.add_argument(
        "--ping", action="store_true",
        help="Include a tiny live probe call in preflight (verifies keys actually work, costs ≤$0.001)",
    )
    return p.parse_args()


def _print_cost_table(report, title: str = "Estimated cost") -> None:
    print(f"\n== {title} ==")
    for label, amount in report.cost_breakdown.items():
        print(f"  {label:<10} ${amount:.4f}")
    print(f"  {'Total':<10} ${report.cost_estimate_usd:.4f}")
    print(f"  LLM calls:  {report.estimated_llm_calls}")
    print(f"  Images:     {report.estimated_images}")


def _confirm_spend(report, skip_prompt: bool) -> bool:
    if skip_prompt:
        print("[--confirm passed, skipping interactive prompt]")
        return True
    # Some environments (Claude Code bash tool, CI, < /dev/null) present
    # a stdin that looks TTY-like but raises EOFError on input(). Catch it
    # and give a useful hint instead of the raw trace.
    print("\nThis run will call real APIs and incur real charges.")
    try:
        resp = input(f"Proceed with estimated ~${report.cost_estimate_usd:.3f}? [y/N] ").strip().lower()
    except EOFError:
        print(
            "\n[Stdin closed - cannot prompt interactively]\n"
            "Re-run with --confirm to skip the prompt and acknowledge the\n"
            f"estimated spend (~${report.cost_estimate_usd:.3f}) explicitly."
        )
        return False
    return resp == "y"


async def _run_pipeline(
    theme: str, output: Path, text_only: bool, max_scenes: int, num_characters: int,
) -> tuple[dict, TokenTracker]:
    """Run the full graph once. Returns (final_state, per-job tracker)."""
    tracker = TokenTracker()
    token = current_tracker.set(tracker)
    try:
        trace = reset_trace()
        pipeline = create_pipeline()
        state = initial_state(
            theme=theme,
            output_dir=str(output),
            text_only=text_only,
            max_scenes=max_scenes,
            num_characters=num_characters,
        )
        final_state: dict = {}
        async for update in pipeline.astream(state, stream_mode="updates"):
            for node_name, chunk in update.items():
                if node_name != "__end__":
                    logger.info(f"-> {node_name}")
                if isinstance(chunk, dict):
                    final_state.update(chunk)
        # Save trace alongside output
        try:
            trace.save(output)
        except Exception as e:  # trace is best-effort
            logger.warning(f"Trace save failed: {e}")
        return final_state, tracker
    finally:
        current_tracker.reset(token)


def _write_run_meta(
    output: Path,
    args: argparse.Namespace,
    preflight_report,
    tracker: TokenTracker,
    wall_time_s: float,
    final_state: dict,
) -> None:
    """Persist post-run metadata next to the Ren'Py project."""
    script = final_state.get("vn_script")
    meta = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "theme": args.theme,
        "max_scenes": args.max_scenes,
        "num_characters": args.characters,
        "text_only": args.text_only,
        "wall_time_seconds": round(wall_time_s, 1),
        "preflight": {
            "estimated_cost_usd": preflight_report.cost_estimate_usd,
            "estimated_llm_calls": preflight_report.estimated_llm_calls,
            "estimated_images": preflight_report.estimated_images,
            "breakdown": preflight_report.cost_breakdown,
        },
        "actual": {
            "token_usage": tracker.summary_dict(),
            "estimated_cost_usd": round(tracker.estimated_cost(), 4),
        },
        "script": {
            "title": script.title if script else None,
            "scene_count": len(script.scenes) if script else 0,
            "character_count": len(final_state.get("characters", {})),
        },
        "errors": final_state.get("errors", []),
    }
    meta_path = output / "run_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRun metadata -> {meta_path}")


async def _main_async(args: argparse.Namespace) -> int:
    settings = get_settings()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output_root / f"vn_{timestamp}"

    # -- 1. Preflight --
    print(f"== Preflight: {args.theme!r} -> {output}")
    report = await check_readiness(
        settings,
        max_scenes=args.max_scenes,
        num_characters=args.characters,
        text_only=args.text_only,
        output_dir=output,
        ping=args.ping,
    )
    _print_cost_table(report)
    if not report.passed:
        print("\n[X] Preflight FAILED - fix these before re-running:")
        for err in report.errors:
            print(f"  - {err}")
        return 2
    for warn in report.warnings:
        print(f"  ! {warn}")

    # -- 2. Confirm --
    if not _confirm_spend(report, skip_prompt=args.confirm):
        print("Aborted by user (no API calls made).")
        return 0

    # -- 3. Run --
    print(f"\n== Running pipeline (models: dir={settings.llm_director_model}, "
          f"writer={settings.llm_writer_model}, reviewer={settings.llm_reviewer_model}, "
          f"image={settings.image_provider}/{settings.image_model})")
    t0 = time.perf_counter()
    try:
        final_state, tracker = await _run_pipeline(
            args.theme, output, args.text_only, args.max_scenes, args.characters,
        )
    except Exception as e:
        wall = time.perf_counter() - t0
        print(f"\n[X] Pipeline failed after {wall:.1f}s: {e}")
        logger.exception("Pipeline error")
        return 1
    wall = time.perf_counter() - t0

    script = final_state.get("vn_script")
    characters = final_state.get("characters", {})
    if not script:
        print("\n[X] No script produced - inspect logs above.")
        _write_run_meta(output, args, report, tracker, wall, final_state)
        return 1

    # -- 4. Build Ren'Py project --
    output.mkdir(parents=True, exist_ok=True)
    build_project(script, characters, output)

    # -- 5. Summary + meta dump --
    actual_cost = tracker.estimated_cost()
    delta = actual_cost - report.cost_estimate_usd
    print(f"\n[OK] Done in {wall:.1f}s")
    print(f"  Title:        {script.title}")
    print(f"  Scenes:       {len(script.scenes)}")
    print(f"  Characters:   {len(characters)}")
    print(f"  Estimated:    ${report.cost_estimate_usd:.4f}")
    print(f"  Actual (LLM): ${actual_cost:.4f}  ({'+' if delta >= 0 else ''}{delta:.4f})")
    print(f"  Output:       {output.resolve()}")
    print(f"\nRen'Py: launch the Ren'Py SDK and point it at {output.resolve()}")

    _write_run_meta(output, args, report, tracker, wall, final_state)
    return 0


def main() -> None:
    args = _parse_args()
    sys.exit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
