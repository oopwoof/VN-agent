"""Phase 13-1 Step 7 + Phase 13-2 Step 4b-6: long-VN smoke + parallel benchmark.

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

ZERO-COST STRUCTURAL DRY RUN (50-scene dry run round):
  uv run python scripts/smoke_longvn.py --mock --scenes 50 --concurrent 5 --text-only
      Runs the same graph end-to-end against the VN_MOCK_SYNTH mock
      synthesizer: no keys, no --confirm, no spend. Validates the
      ORCHESTRATION (chapters, state_timeline, DAG waves, thinking,
      rollups, parallel writer overlap) — it cannot validate context
      degradation, output quality, cost, or rate-limit behavior; those
      still need the real-API tiers above.

PARALLEL WRITER (Phase 13-2 Step 4b-6):
  --concurrent N
      Set writer_max_concurrent. N>1 auto-enables thinking_fanout +
      writer_consume_thinking (required by the parallel-path coupling
      validator). N=1 keeps the sequential path (default, byte-identical
      to pre-Phase-13-2 behavior).

  --benchmark
      Run THREE trials back-to-back (concurrent=1, 2, 5) with the same
      theme + scene count and emit a wall-clock comparison table.
      WARNING: 3x the spend of a single run. The wall-clock target on
      20 scenes / concurrent=5 is ≥1.5x speedup vs sequential — bounded
      by Anthropic per-key rate limits, not by code parallelism.

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
  Benchmark mode additionally writes:
    demo_output/smoke_longvn_benchmark_<timestamp>/
      summary.json               # 3 trials × wall_seconds / cost / cache ratio
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
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


def _compute_health_signals(
    n_rotations: int, scene_count: int, wall_minutes: float,
) -> tuple[list[str], str]:
    """Phase 13-3 M0-4: pure helper for stress-test health gating.

    Inputs are post-run observables; returns (signals, status) where
    `status` is "green" (no signals), "yellow" (advisory only), or "red"
    (operator should abort downstream tiers).

    Thresholds chosen for M1's tiered runner (12 → 25 → 50). When a
    cheap tier (12) trips red, skipping the expensive 50-scene tier
    saves ~$10-15.
    """
    signals: list[str] = []

    if n_rotations > 5:
        signals.append(
            f"retry_count={n_rotations} exceeds threshold 5 — Anthropic"
            f" rate-limit pressure too high; recommend reducing concurrent"
            f" or waiting before next tier"
        )

    if scene_count > 0 and n_rotations > scene_count:
        signals.append(
            f"key_rotation_density={n_rotations}/{scene_count} > 1.0 — "
            f"sustained 429 pressure observed"
        )

    expected_minutes = max(1.5, scene_count * 0.3)  # ~18s/scene baseline
    if wall_minutes > expected_minutes * 2:
        signals.append(
            f"wall_minutes={wall_minutes} > 2x expected "
            f"({expected_minutes:.1f}) — runtime degradation"
        )

    # Status: red if a "hard" signal trips, yellow if any signal trips,
    # green otherwise. Hard signals = retry_count threshold + wall blow-up.
    # Density alone is yellow (advisory; not an abort).
    is_red = any(
        ("exceeds threshold" in s) or ("> 2x expected" in s)
        for s in signals
    )
    status = "red" if is_red else ("yellow" if signals else "green")
    return signals, status


def _count_jsonl_lines(path: Path) -> int:
    """Non-blank line count; 0 for a missing/unreadable file. Used to turn
    the cumulative api_key_rotations.jsonl into a per-run delta — reading
    its absolute size attributed every historic run's rotations to the
    current one (a zero-call mock run read as RED off 47 old rows)."""
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not read {path.name}: {e}")
        return 0


def _apply_concurrency_overrides(settings, concurrent: int) -> None:
    """Phase 13-2 Step 4b-6: in-process Settings override for benchmark
    mode, where we re-run the same theme at different concurrency tiers
    in one process and need each trial to see fresh values.

    For concurrent>1 we MUST also flip the thinking-fanout flags on —
    otherwise the parallel writers have no within-wave coordination
    signal (Settings.model_validator enforces this at construction).
    Mutating the existing instance bypasses the validator (Pydantic
    only re-validates assignments when validate_assignment=True), but
    the three flags are set together and consistently, so we satisfy
    the rule by construction.
    """
    settings.writer_max_concurrent = concurrent
    if concurrent > 1:
        settings.enable_thinking_fanout = True
        settings.writer_consume_thinking = True


def _apply_mock_overrides(settings) -> None:
    """--mock: flip on the long-form machinery that defaults off, so the
    dry run exercises it instead of silently skipping it. Same
    post-construction-mutation pattern (and caveat) as
    _apply_concurrency_overrides above."""
    settings.enable_cross_ref_sync = True
    settings.enable_scene_summarization = True


def _mock_structural_issues(script, *, expect_thinking: bool) -> list[str]:
    """Structural FAIL predicates for --mock runs.

    Mock tiers can't assert on cost or cache ratio (both zero), so they
    assert on structure. Each predicate targets a specific silent failure
    this round actually found: the one-fixture-for-every-scene writer
    fallback, the thinking misroute that validated into all-defaults
    SceneThinking, and the rollup misroute that stored dialogue JSON as
    Chapter.summary. Pure function; unit-tested in test_smoke_longvn.py.
    """
    issues: list[str] = []
    if script is None:
        return ["FAIL(mock): no script produced"]

    first_lines = [s.dialogue[0].text for s in script.scenes if s.dialogue]
    if len(set(first_lines)) != len(first_lines):
        issues.append(
            "FAIL(mock): identical dialogue across scenes — the writer "
            "fallback served one fixture for every scene"
        )

    if expect_thinking:
        vacuous = [
            s.id for s in script.scenes
            if s.thinking is None or not s.thinking.writing_intent
        ]
        if vacuous:
            issues.append(
                f"FAIL(mock): vacuous/missing thinking on {len(vacuous)} "
                f"scene(s) (e.g. {vacuous[:3]}) — thinking misroute is back"
            )

    for ch in getattr(script, "chapters", []) or []:
        if not ch.summary:
            issues.append(
                f"FAIL(mock): chapter {ch.chapter_id} rollup summary empty"
            )
            continue
        try:
            parsed = json.loads(ch.summary)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            issues.append(
                f"FAIL(mock): chapter {ch.chapter_id} rollup summary is a "
                f"dialogue JSON array — rollup misroute is back"
            )
    return issues


async def _run(args: argparse.Namespace, *, concurrent: int | None = None,
               output_subdir: Path | None = None) -> dict:
    settings = get_settings()
    theme = args.theme
    text_only = bool(args.text_only)

    effective_concurrent = concurrent if concurrent is not None else args.concurrent
    _apply_concurrency_overrides(settings, effective_concurrent)
    logger.info(
        f"Writer concurrency: {settings.writer_max_concurrent} "
        f"(thinking_fanout={settings.enable_thinking_fanout}, "
        f"consume_thinking={settings.writer_consume_thinking})"
    )

    is_mock = bool(getattr(args, "mock", False))
    gauge = {"cur": 0, "peak": 0}
    _orig_mock_ainvoke = None
    if is_mock:
        from vn_agent.services import mock_llm
        from vn_agent.services.llm import mock_mode_var

        mock_mode_var.set(True)
        os.environ["VN_MOCK_SYNTH"] = "1"
        # Keep the dry run fully offline: SBERT is loaded from the local HF
        # cache anyway, but without this the hub revalidates every file over
        # the network. setdefault so an operator can override on a machine
        # that genuinely needs a first-time download.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        _apply_mock_overrides(settings)
        logger.info(
            "Mock mode: mock_mode_var=True, VN_MOCK_SYNTH=1, HF offline, "
            "cross_ref_sync + scene_summarization forced on"
        )

        # Peak-writer-concurrency gauge. mock_ainvoke never awaits, so each
        # coroutine runs to completion the first time it's scheduled and a
        # naive counter would read 1 even under asyncio.gather. The 5ms
        # sleep yields control inside each call so overlap becomes
        # observable. llm.ainvoke_llm resolves mock_llm.mock_ainvoke as a
        # module attribute per call, so this harness-local patch takes
        # effect without touching production code.
        _orig_mock_ainvoke = mock_llm.mock_ainvoke

        async def _gauged(system_prompt, user_prompt, schema=None,
                          model=None, caller="llm", **kwargs):
            is_writer = caller.startswith("writer/")
            if is_writer:
                gauge["cur"] += 1
                gauge["peak"] = max(gauge["peak"], gauge["cur"])
            try:
                await asyncio.sleep(0.005)
                return await _orig_mock_ainvoke(
                    system_prompt, user_prompt, schema=schema,
                    model=model, caller=caller, **kwargs,
                )
            finally:
                if is_writer:
                    gauge["cur"] -= 1

        mock_llm.mock_ainvoke = _gauged

    # Output dir
    if output_subdir is not None:
        output_dir = output_subdir
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output_dir = Path("demo_output") / f"smoke_longvn_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output: {output_dir}")

    # Preflight — skipped in mock: check_readiness hard-fails on a missing
    # API key (preflight.py) before the mock gate could ever matter.
    if is_mock:
        logger.info("Mock mode: skipping preflight (no keys, no spend)")
    else:
        logger.info("Running preflight checks…")
        readiness = await check_readiness(
            settings=settings,
            max_scenes=args.scenes,
            num_characters=args.characters,
            text_only=text_only,
            output_dir=output_dir,
        )
        if not readiness.passed:
            logger.error(f"Preflight failed: {readiness.errors}")
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
    rotations_path = Path.cwd() / "api_key_rotations.jsonl"
    rotations_before = _count_jsonl_lines(rotations_path)
    t0 = time.perf_counter()
    try:
        final_state = await graph.ainvoke(state, {"recursion_limit": 100})
    finally:
        if _orig_mock_ainvoke is not None:
            from vn_agent.services import mock_llm
            mock_llm.mock_ainvoke = _orig_mock_ainvoke
    wall = time.perf_counter() - t0
    logger.info(f"Pipeline complete in {wall:.1f}s ({wall/60:.1f} min)")

    # Validate Phase 13-1 targets
    script = final_state.get("vn_script")
    report: dict = {
        "wall_seconds": round(wall, 1),
        "wall_minutes": round(wall / 60, 2),
        "writer_max_concurrent": effective_concurrent,
        "scene_count": len(script.scenes) if script else 0,
        "chapter_count": len(getattr(script, "chapters", []) or []),
        "state_timeline_count": len(getattr(script, "state_timeline", []) or []),
        "theme": theme,
        "output_dir": str(output_dir),
        "errors": final_state.get("errors", []),
        # Phase 13-2 Step 4e: warnings split from errors. StructureReviewer
        # findings now flow to warnings instead of errors so [PASS] runs
        # don't read as failures in run_metrics.json.
        "warnings": final_state.get("warnings", []),
        "mock": is_mock,
    }
    if is_mock:
        report["peak_writer_concurrency"] = gauge["peak"]
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
    if is_mock:
        assertions.extend(_mock_structural_issues(
            script,
            expect_thinking=(
                settings.enable_thinking_fanout
                and args.scenes >= settings.thinking_fanout_min_scenes
            ),
        ))
        if effective_concurrent > 1 and gauge["peak"] <= 1:
            assertions.append(
                f"FAIL(mock): peak_writer_concurrency={gauge['peak']} — "
                f"requested concurrent={effective_concurrent} but scene "
                f"writes never overlapped"
            )
        if (
            settings.enable_cross_ref_sync
            and args.scenes >= settings.cross_ref_sync_min_scenes
            and not (output_dir / "cross_ref_conflicts.jsonl").exists()
        ):
            assertions.append(
                "FAIL(mock): cross_ref_conflicts.jsonl missing — shared "
                "context_deps never collided, cross_ref_sync validated nothing"
            )
    report["assertions"] = assertions

    # Phase 13-3 M0-4: stability/health signals so M1's tiered stress runner
    # (12 → 25 → 50) can gate on this run's dirtiness. Delta, not absolute:
    # the jsonl is cumulative across every run in this CWD.
    n_rotations = max(0, _count_jsonl_lines(rotations_path) - rotations_before)
    report["key_rotation_count"] = n_rotations

    degradation_signals, health_status = _compute_health_signals(
        n_rotations=n_rotations,
        scene_count=args.scenes,
        wall_minutes=report["wall_minutes"],
    )
    report["degradation_signals"] = degradation_signals
    report["health_status"] = health_status

    # Persist run metrics
    (output_dir / "run_metrics.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Phase 13-3 M0-4: respect --abort-on-degradation by exiting non-zero
    # so a tier-runner shell loop (M1) can `break` on first red signal
    # without parsing JSON.
    if (
        getattr(args, "abort_on_degradation", False)
        and report["health_status"] == "red"
    ):
        logger.error(
            f"[abort] degradation signals tripped: {degradation_signals}"
        )
        raise SystemExit(3)

    return report


_BENCHMARK_TIERS = (1, 2, 5)


async def _run_benchmark(args: argparse.Namespace) -> dict:
    """Phase 13-2 Step 4b-6: 3-tier wall-clock benchmark.

    Runs concurrent=1, 2, 5 sequentially against the same theme + scene
    count. Each trial uses a unique output subdirectory under one
    benchmark root so artifacts don't collide. Returns the aggregated
    summary; emits one row per trial to stdout as it goes so the user
    can monitor progress without tailing a file.

    Speedup target on 20 scenes / concurrent=5: ≥1.5x vs concurrent=1.
    Anthropic per-key tier rate limits are the real ceiling (not the
    Semaphore bound), so a 5x slot count does NOT mean a 5x speedup.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    bench_root = Path("demo_output") / f"smoke_longvn_benchmark_{stamp}"
    bench_root.mkdir(parents=True, exist_ok=True)
    logger.info(f"Benchmark root: {bench_root}")

    trials: list[dict] = []
    for tier in _BENCHMARK_TIERS:
        print(f"\n=== Trial: concurrent={tier} ===")
        sub = bench_root / f"trial_concurrent_{tier}"
        report = await _run(args, concurrent=tier, output_subdir=sub)
        trials.append({
            "concurrent": tier,
            "wall_seconds": report["wall_seconds"],
            "wall_minutes": report["wall_minutes"],
            "scene_count": report["scene_count"],
            "total_cost_usd": report.get("total_cost_usd"),
            "cache_read_ratio": report.get("cache_read_ratio"),
            "errors": report["errors"],
            "output_dir": report["output_dir"],
        })
        print(
            f"  wall={report['wall_minutes']} min, "
            f"cost=${report.get('total_cost_usd', '?')}, "
            f"cache_read={report.get('cache_read_ratio', '?')}"
        )

    # Speedup ratios relative to concurrent=1.
    base = trials[0]["wall_seconds"]
    for t in trials:
        t["speedup_vs_sequential"] = (
            round(base / t["wall_seconds"], 2)
            if base and t["wall_seconds"] else None
        )

    summary = {
        "scenes": args.scenes,
        "characters": args.characters,
        "theme": args.theme,
        "text_only": args.text_only,
        "tiers": list(_BENCHMARK_TIERS),
        "trials": trials,
        "speedup_target_concurrent_5": "≥1.5x vs concurrent=1",
    }
    (bench_root / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def _print_benchmark_table(summary: dict) -> None:
    print("\n=== Benchmark summary ===")
    print(f"{'concurrent':>10} | {'wall_min':>9} | {'cost_usd':>9} | "
          f"{'cache_read':>10} | {'speedup':>8}")
    print("-" * 60)
    for t in summary["trials"]:
        cost = t.get("total_cost_usd")
        cost_s = f"{cost:.2f}" if cost is not None else "?"
        cr = t.get("cache_read_ratio")
        cr_s = f"{cr:.2f}" if cr is not None else "?"
        sp = t.get("speedup_vs_sequential")
        sp_s = f"{sp}x" if sp is not None else "?"
        print(f"{t['concurrent']:>10} | {t['wall_minutes']:>9.2f} | "
              f"{cost_s:>9} | {cr_s:>10} | {sp_s:>8}")


def main() -> None:
    # Windows consoles default to the system codepage (e.g. GBK), which
    # mangles Chinese theme text in the dry-run summary printed below — same
    # fix as scripts/update_docs.py. Without this, --theme "<中文>" prints as
    # mojibake even though the underlying str is correctly decoded (cosmetic
    # only, but it's exactly what someone eyeballs before typing --confirm).
    # Scoped to main() (not module level): reassigning sys.stdout/stderr at
    # import time corrupts pytest's own capture bookkeeping for every test
    # collected afterward in the same process (confirmed — running the full
    # suite after tests/test_scripts/test_smoke_longvn.py imports this
    # module previously cascaded into ~500 spurious "I/O operation on closed
    # file" errors). main() only runs when this script is actually invoked
    # as a program, never on import.
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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
    parser.add_argument(
        "--concurrent", type=int, default=1,
        help="writer_max_concurrent. >1 auto-enables thinking_fanout + "
             "writer_consume_thinking (Phase 13-2 Step 4b-6).",
    )
    parser.add_argument(
        "--benchmark", action="store_true",
        help="Run 3 trials at concurrent=1,2,5 back-to-back. 3x the spend.",
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Zero-cost structural dry run against the VN_MOCK_SYNTH mock "
             "synthesizer. No keys, no --confirm, no spend. Validates "
             "orchestration only — not quality, cost, or rate limits.",
    )
    parser.add_argument("--confirm", action="store_true",
                        help="Actually run. Without this, prints cost estimate and exits.")
    parser.add_argument(
        "--abort-on-degradation", action="store_true",
        help="(Phase 13-3 M0-4) Exit non-zero (code 3) if post-run health "
             "signals tripped: retry_count > 5, key_rotation_density > 1, or "
             "wall_minutes > 2x expected. Used by M1 stress-test tier-runner "
             "to skip subsequent tiers when the current one shows instability.",
    )
    args = parser.parse_args()

    if args.concurrent < 1:
        raise SystemExit("--concurrent must be >= 1")
    if args.mock and args.benchmark:
        raise SystemExit(
            "--benchmark is real-API-only: mock wall-clock speedups are "
            "fiction. Use --mock alone — the peak_writer_concurrency gauge "
            "answers the did-it-parallelize question."
        )

    multiplier = len(_BENCHMARK_TIERS) if args.benchmark else 1
    est_cost = 0.0 if args.mock else (
        _estimate_cost(args.scenes, args.text_only) * multiplier
    )
    print("\n=== smoke_longvn.py ===")
    print(f"  scenes:        {args.scenes}")
    print(f"  characters:    {args.characters}")
    print(f"  text_only:     {args.text_only}")
    if args.benchmark:
        print(f"  mode:          BENCHMARK ({len(_BENCHMARK_TIERS)} trials: "
              f"concurrent={list(_BENCHMARK_TIERS)})")
    else:
        print(f"  concurrent:    {args.concurrent}")
    print(f"  est. cost:     ~${est_cost}" + ("  (mock: zero spend)" if args.mock else ""))
    print(f"  theme:         {args.theme[:80]}")

    if not args.confirm and not args.mock:
        print("\n[DRY RUN] Rerun with --confirm to actually spend money.")
        return

    print("\nRunning…\n")
    if args.benchmark:
        summary = asyncio.run(_run_benchmark(args))
        _print_benchmark_table(summary)
        # Surface trial-level FAILs as a non-zero exit so CI / users notice.
        bad = [t for t in summary["trials"] if t["errors"]]
        if bad:
            print(f"\n[FAIL] {len(bad)} trial(s) reported errors.")
            raise SystemExit(1)
        print("\n[PASS] Benchmark complete.")
        return

    report = asyncio.run(_run(args))
    print("\n=== Results ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # Phase 13-3 M0-4: surface degradation signals visibly so M1 tier-runner
    # operators see them at-a-glance without parsing JSON.
    health = report.get("health_status", "green")
    if health != "green":
        signals = report.get("degradation_signals", []) or []
        print(f"\n[{health.upper()}] Health signals:")
        for s in signals:
            print(f"  - {s}")
    if report.get("assertions"):
        print("\n[FAIL] Acceptance assertions violated:")
        for msg in report["assertions"]:
            print(f"  - {msg}")
        raise SystemExit(1)
    print("\n[PASS] All acceptance targets met.")


if __name__ == "__main__":
    main()
