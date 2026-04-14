"""Sprint 7-4: 3-mode x 3-theme quantitative sweep.

For each combination of {mode, theme}:
  1. Set writer_mode + corpus_path to simulate the mode
  2. Run scripts/run_real_demo.py (Sonnet pipeline, text-only, 6 scenes)
  3. Call eval_strategy_adherence on the produced vn_script.json
  4. Record per-scene scores

Aggregate into demo_output/sweep_results.md + demo_output/sweep_raw.json.

Why a separate script and not pytest parametrize: each cell is a real
API call (~$0.35) and takes ~9 minutes. We want resumability (skip
cells already done), explicit --confirm for spend, and a human-readable
markdown report that can be cited in docs/RESUME.md.

Sprint 8-3 update: 4-mode x 2-theme = 8 cells. Baselines added:
  - baseline_single: one Sonnet call, skips the graph entirely (~$0.05)
  - baseline_self_refine: draft + self-critique + revise (~$0.15)
Plus literary, action (full graph, ~$0.50 each).
Total 8-cell budget: ~$2.40 + ~$0.10 judge cost ≈ $2.50.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean as _mean
from statistics import pstdev

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MODES = ["literary", "action", "baseline_single", "baseline_self_refine"]
THEMES = [
    ("lighthouse", "A lighthouse keeper during a storm"),
    ("dragon",     "Dragon slays the warrior"),
]

SWEEP_DIR = ROOT / "demo_output" / "sweep"
RAW_PATH = SWEEP_DIR / "sweep_raw.json"
REPORT_PATH = SWEEP_DIR / "sweep_results.md"


def _cell_dir(mode: str, theme_id: str) -> Path:
    return SWEEP_DIR / f"{mode}__{theme_id}"


def _cell_already_done(cell_dir: Path) -> bool:
    """A cell counts as done if it has a run_meta.json AND scored.json."""
    return (cell_dir / "run_meta.json").exists() and (cell_dir / "scored.json").exists()


def _run_baseline_cell(mode: str, theme: str, cell_dir: Path) -> Path | None:
    """Run a baseline (single-shot or self-refine) in-process, then write a
    minimal run_meta.json + vn_script.json so the rest of the sweep plumbing
    (judging, reporting) doesn't need mode-specific branches downstream.
    """
    from vn_agent.agents.baseline_runners import (
        run_baseline_self_refine,
        run_baseline_single,
    )
    from vn_agent.services.token_tracker import TokenTracker, current_tracker

    run_dir = cell_dir / f"vn_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    tracker = TokenTracker()
    token = current_tracker.set(tracker)
    t0 = time.perf_counter()
    try:
        if mode == "baseline_single":
            result = asyncio.run(run_baseline_single(theme, max_scenes=6, num_characters=3))
        else:
            result = asyncio.run(run_baseline_self_refine(theme, max_scenes=6, num_characters=3))
    except Exception as e:
        print(f"  [FAIL] baseline {mode} crashed: {e}")
        return None
    finally:
        current_tracker.reset(token)
    wall = time.perf_counter() - t0

    # Persist vn_script.json
    (run_dir / "vn_script.json").write_text(
        result.script.model_dump_json(indent=2), encoding="utf-8",
    )
    if result.characters:
        (run_dir / "characters.json").write_text(
            json.dumps(
                {cid: c.model_dump() for cid, c in result.characters.items()},
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # Minimal run_meta.json matching the full-graph shape enough for
    # downstream aggregation
    usage = tracker.summary_dict()
    actual_cost = tracker.estimated_cost()
    meta = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "theme": theme,
        "mode": mode,
        "max_scenes": 6,
        "num_characters": 3,
        "text_only": True,
        "wall_time_seconds": round(wall, 1),
        "actual": {
            "token_usage": usage,
            "estimated_cost_usd": round(actual_cost, 4),
        },
        "script": {
            "title": result.script.title,
            "scene_count": len(result.script.scenes),
            "character_count": len(result.characters),
        },
        "errors": result.errors,
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(
        f"  [OK] baseline {mode} wall={wall:.1f}s "
        f"cost=${actual_cost:.4f} scenes={len(result.script.scenes)}"
    )
    return run_dir


def _run_one_cell(mode: str, theme_id: str, theme: str, force: bool) -> dict:
    """Run pipeline + judge for one (mode, theme) cell. Returns summary dict."""
    cell_dir = _cell_dir(mode, theme_id)
    cell_dir.mkdir(parents=True, exist_ok=True)

    if _cell_already_done(cell_dir) and not force:
        print(f"  [SKIP] {mode}/{theme_id} — already has run_meta.json + scored.json")
        return _load_cell_summary(cell_dir)

    print(f"\n== CELL: mode={mode} theme={theme_id} ({theme!r}) ==")
    t0 = time.perf_counter()

    # ── 1. Dispatch by mode ──────────────────────────────────────────────
    if mode in ("baseline_single", "baseline_self_refine"):
        # In-process baseline; no full graph.
        run_dir = _run_baseline_cell(mode, theme, cell_dir)
        if run_dir is None:
            wall = time.perf_counter() - t0
            return {"mode": mode, "theme": theme_id, "error": "baseline failed"}
        meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
        wall = time.perf_counter() - t0
    else:
        # Full graph via subprocess, env-controlled writer_mode.
        env = os.environ.copy()
        if mode == "literary":
            env["WRITER_MODE"] = "literary"
        elif mode == "action":
            env["WRITER_MODE"] = "action"
        elif mode == "no_rag":
            env["WRITER_MODE"] = "literary"
            env["CORPUS_PATH"] = ""

        cmd = [
            sys.executable, str(ROOT / "scripts" / "run_real_demo.py"),
            "--theme", theme,
            "--text-only", "--confirm",
            "--max-scenes", "6",
            "--output-root", str(cell_dir),
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=ROOT)
        wall = time.perf_counter() - t0
        if result.returncode != 0:
            print(f"  [FAIL] exit={result.returncode} wall={wall:.1f}s")
            print("  stderr tail:", result.stderr[-400:])
            return {"mode": mode, "theme": theme_id, "error": result.stderr[-400:]}

        run_subdirs = sorted([p for p in cell_dir.glob("vn_*") if p.is_dir()])
        if not run_subdirs:
            return {"mode": mode, "theme": theme_id, "error": "No vn_* output directory"}
        run_dir = run_subdirs[-1]
        meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))

    # ── 3. Score with eval_strategy_adherence (in-process) ────────────────
    print(f"  [OK] pipeline wall={wall:.1f}s cost=${meta['actual']['estimated_cost_usd']:.4f}")
    print("  Scoring ...")

    from vn_agent.eval.strategy_metrics import compute_signals  # noqa: E402
    from vn_agent.schema.script import VNScript  # noqa: E402

    sys.path.insert(0, str(ROOT / "scripts"))
    from eval_strategy_adherence import _judge_scene  # type: ignore

    script = VNScript.model_validate_json((run_dir / "vn_script.json").read_text(encoding="utf-8"))
    scored = []
    for scene in script.scenes:
        strategy = scene.narrative_strategy or "drift"
        judged = asyncio.run(_judge_scene(scene, strategy))
        # Sprint 8-2: also include rule-based metrics
        signals = compute_signals(scene)
        sig_dict = signals.as_dict()
        row = {
            "scene_id": scene.id,
            "strategy": strategy,
            "score": judged.get("score_primary", 0),
            "reason": judged.get("reason_primary", ""),
            **judged,
            "rule_signals": sig_dict,
            "rule_for_assigned": round(sig_dict.get(strategy, 0.0), 3),
            "rule_best_match": signals.best_match(),
        }
        scored.append(row)
        sec = judged.get("score_secondary")
        sec_str = f" sec={sec}" if sec is not None else ""
        print(
            f"    {scene.id:<30} {strategy:<12} "
            f"primary={row['score']}{sec_str} rule={row['rule_for_assigned']:.2f}"
        )

    # Persist per-cell scored results
    (cell_dir / "scored.json").write_text(
        json.dumps({"mode": mode, "theme_id": theme_id, "run_dir": str(run_dir),
                    "meta": meta, "scored": scored}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    valid_scores = [s["score"] for s in scored if s["score"] > 0]
    mean = (sum(valid_scores) / len(valid_scores)) if valid_scores else 0.0
    return {
        "mode": mode,
        "theme": theme_id,
        "scene_count": len(scored),
        "mean_score": round(mean, 2),
        "cost_usd": meta["actual"]["estimated_cost_usd"],
        "wall_s": meta["wall_time_seconds"],
        "scores": [s["score"] for s in scored],
        "scored": scored,
    }


def _load_cell_summary(cell_dir: Path) -> dict:
    blob = json.loads((cell_dir / "scored.json").read_text(encoding="utf-8"))
    mode = blob["mode"]
    theme_id = blob["theme_id"]
    meta = blob["meta"]
    scored = blob["scored"]
    valid = [s["score"] for s in scored if s["score"] > 0]
    mean = (sum(valid) / len(valid)) if valid else 0.0
    return {
        "mode": mode,
        "theme": theme_id,
        "scene_count": len(scored),
        "mean_score": round(mean, 2),
        "cost_usd": meta["actual"]["estimated_cost_usd"],
        "wall_s": meta["wall_time_seconds"],
        "scores": [s["score"] for s in scored],
        "scored": scored,
    }


def _write_report(cells: list[dict]) -> None:
    lines = [
        "# Sprint 7-4 Quantitative Sweep Results",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Total cells: {len(cells)}",
        f"Total cost: ${sum(c.get('cost_usd', 0) for c in cells):.4f}",
        "",
        "## Per-cell summary",
        "",
        "| mode | theme | scenes | mean | scores | cost | wall |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        if "error" in c:
            lines.append(f"| {c['mode']} | {c['theme']} | — | ERROR | — | — | — |")
            continue
        lines.append(
            f"| {c['mode']} | {c['theme']} | {c['scene_count']} "
            f"| **{c['mean_score']}** | {c['scores']} "
            f"| ${c['cost_usd']:.3f} | {c['wall_s']:.0f}s |"
        )
    lines += ["", "## Aggregate by mode", ""]
    lines.append("| mode | n | mean | std (approx) |")
    lines.append("|---|---|---|---|")
    for mode in MODES:
        all_scores = [
            s for c in cells if c.get("mode") == mode
            for s in c.get("scores", []) if s > 0
        ]
        if all_scores:
            m = round(_mean(all_scores), 2)
            sd = round(pstdev(all_scores), 2) if len(all_scores) > 1 else 0.0
            lines.append(f"| {mode} | {len(all_scores)} | {m} | {sd} |")

    lines += ["", "## Aggregate by mode × theme", ""]
    lines.append("| mode \\ theme | " + " | ".join(t[0] for t in THEMES) + " |")
    lines.append("|---|" + "|".join(["---"] * len(THEMES)) + "|")
    for mode in MODES:
        row = [mode]
        for theme_id, _ in THEMES:
            cell = next((c for c in cells if c.get("mode") == mode and c.get("theme") == theme_id), None)
            row.append(f"{cell['mean_score']}" if cell and "mean_score" in cell else "—")
        lines.append("| " + " | ".join(row) + " |")

    lines += ["", "## Per-strategy aggregate (across all cells)", ""]
    lines.append("| strategy | mode | n | mean |")
    lines.append("|---|---|---|---|")
    by_strat_mode: dict[tuple[str, str], list[int]] = {}
    for c in cells:
        for row in c.get("scored", []):
            if row["score"] > 0:
                key = (row["strategy"], c["mode"])
                by_strat_mode.setdefault(key, []).append(row["score"])
    for (strat, mode), scores in sorted(by_strat_mode.items()):
        lines.append(f"| {strat} | {mode} | {len(scores)} | {sum(scores)/len(scores):.2f} |")

    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport -> {REPORT_PATH}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--confirm", action="store_true", help="Acknowledge ~$3.15 spend")
    p.add_argument("--force", action="store_true", help="Re-run cells even if already scored")
    p.add_argument("--only-mode", choices=MODES, help="Restrict sweep to one mode")
    p.add_argument("--only-theme", choices=[t[0] for t in THEMES], help="Restrict sweep to one theme")
    args = p.parse_args()

    SWEEP_DIR.mkdir(parents=True, exist_ok=True)

    cells_to_run = [
        (m, tid, th)
        for m in MODES if (args.only_mode is None or m == args.only_mode)
        for tid, th in THEMES if (args.only_theme is None or tid == args.only_theme)
    ]

    # Count cells still needing API spend
    to_spend = sum(1 for m, tid, _ in cells_to_run if not (_cell_already_done(_cell_dir(m, tid)) and not args.force))
    est_cost = to_spend * 0.35
    print(f"Sweep: {len(cells_to_run)} cells total; {to_spend} need API calls (est. ~${est_cost:.2f})")

    if to_spend > 0 and not args.confirm:
        print("Re-run with --confirm to proceed with API spend.")
        return 2

    cells: list[dict] = []
    for mode, theme_id, theme in cells_to_run:
        summary = _run_one_cell(mode, theme_id, theme, force=args.force)
        cells.append(summary)
        # Persist raw progress after every cell — resumable if we crash
        RAW_PATH.write_text(json.dumps(cells, indent=2, ensure_ascii=False), encoding="utf-8")

    _write_report(cells)
    return 0


if __name__ == "__main__":
    sys.exit(main())
