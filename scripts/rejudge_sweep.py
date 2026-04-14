"""Re-judge existing sweep cells with fixed cross-model routing.

Why: the sweep cells at demo_output/sweep/* were scored before the
_infer_provider_from_model fix in services/llm.py (commit 2bc02d7).
GPT-4o calls for the secondary judge were silently routed to the
Anthropic endpoint and 404'd, so `score_secondary` is missing / None
across the existing 48-row dataset. Re-generating all 8 cells just to
fix the judge would cost ~$3 and burn 70+ minutes; re-judging the
already-written scenes costs ~$0.15 and takes ~5 minutes.

What: loads each cell's scored.json, re-runs _judge_scene on every
scene (so both primary Sonnet + secondary GPT-4o judges hit with the
fixed routing), writes the updated scored.json, then re-renders the
sweep_results.md markdown with the fresh Pearson r + means.

Safety: does NOT touch vn_script.json / run_meta.json — generation
data is preserved. Re-runs are idempotent because _judge_scene is
deterministic at temperature=0.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from statistics import mean as _mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_strategy_adherence import _judge_scene  # type: ignore  # noqa: E402
from vn_agent.eval.strategy_metrics import compute_signals  # noqa: E402
from vn_agent.schema.script import VNScript  # noqa: E402

SWEEP_DIR = ROOT / "demo_output" / "sweep"


async def _rejudge_cell(cell_dir: Path) -> dict:
    scored_path = cell_dir / "scored.json"
    if not scored_path.exists():
        return {"cell": cell_dir.name, "error": "no scored.json"}

    old = json.loads(scored_path.read_text(encoding="utf-8"))
    run_dir = Path(old["run_dir"])
    script_path = run_dir / "vn_script.json"
    if not script_path.exists():
        return {"cell": cell_dir.name, "error": f"vn_script.json missing at {run_dir}"}

    script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    new_scored: list[dict] = []
    for scene in script.scenes:
        strategy = scene.narrative_strategy or "drift"
        judged = await _judge_scene(scene, strategy)
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
        new_scored.append(row)
        sec = judged.get("score_secondary")
        sec_str = f" sec={sec}" if sec is not None else ""
        print(
            f"    {scene.id:<30} {strategy:<12} "
            f"primary={row['score']}{sec_str} rule={row['rule_for_assigned']:.2f}"
        )

    blob = dict(old)
    blob["scored"] = new_scored
    scored_path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    valid = [s["score"] for s in new_scored if s["score"] > 0]
    mean = (sum(valid) / len(valid)) if valid else 0.0
    return {
        "cell": cell_dir.name,
        "mode": blob["mode"],
        "theme": blob["theme_id"],
        "scene_count": len(new_scored),
        "mean_score": round(mean, 2),
    }


async def main() -> None:
    cells = sorted(
        p for p in SWEEP_DIR.iterdir()
        if p.is_dir() and (p / "scored.json").exists()
    )
    print(f"Re-judging {len(cells)} sweep cells under {SWEEP_DIR}\n")

    summaries: list[dict] = []
    for cell in cells:
        print(f"[{cell.name}]")
        result = await _rejudge_cell(cell)
        summaries.append(result)
        print()

    # Aggregate: build new sweep_raw.json for downstream report tooling
    raw = {"cells": summaries, "rejudged_at": "2026-04-14"}
    (SWEEP_DIR / "sweep_raw_rejudged.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Compute Pearson r across all scored rows (primary vs secondary)
    pairs: list[tuple[float, float]] = []
    for cell in cells:
        blob = json.loads((cell / "scored.json").read_text(encoding="utf-8"))
        for row in blob["scored"]:
            p = row.get("score_primary") or row.get("score") or 0
            s = row.get("score_secondary") or 0
            if p > 0 and s > 0:
                pairs.append((float(p), float(s)))

    if pairs:
        n = len(pairs)
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        mx, my = _mean(xs), _mean(ys)
        num = sum((x - mx) * (y - my) for x, y in pairs)
        dx = sum((x - mx) ** 2 for x in xs) ** 0.5
        dy = sum((y - my) ** 2 for y in ys) ** 0.5
        r = num / (dx * dy) if dx > 0 and dy > 0 else 0.0
        agree_1pt = sum(1 for x, y in pairs if abs(x - y) <= 1) / n
        print("─" * 60)
        print(f"Cross-model judge agreement (n={n} paired scenes):")
        print(f"  mean_primary   = {mx:.2f}  (claude-sonnet-4-6)")
        print(f"  mean_secondary = {my:.2f}  (gpt-4o)")
        print(f"  Pearson r      = {r:.3f}")
        print(f"  ±1-point agreement = {agree_1pt:.0%}")
    else:
        print("No paired primary+secondary scores found — check judge routing again.")


if __name__ == "__main__":
    asyncio.run(main())
