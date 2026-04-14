"""Sprint 6-14: LLM-as-judge quantitative RAG ablation.

For each scene in two saved runs, ask Haiku:
  "Does this dialogue exhibit the <strategy> mechanism (per the
   annotation-guideline definition)? Score 1-5."

Then print the per-strategy and aggregate mean score diff between
RAG=off (run 1) and RAG=on (run 2). This converts vague "looks
different" observations into a concrete number we can cite.

Cost: 2 runs × N scenes × 1 Haiku call ≈ $0.003 for 6-scene runs.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vn_agent.config import get_settings  # noqa: E402
from vn_agent.schema.script import VNScript  # noqa: E402
from vn_agent.services.llm import ainvoke_llm  # noqa: E402
from vn_agent.strategies.narrative import STRATEGIES, StrategyType  # noqa: E402

RUNS = {
    "no_rag":   Path("demo_output/vn_20260413_163809"),
    "rag_old":  Path("demo_output/vn_20260413_172957"),
}


JUDGE_SYSTEM = """You are a narrative mechanism judge trained on the COLX_523 \
annotation guideline. Given a 12-line visual novel scene dialogue and an \
assigned narrative strategy, you score how well the dialogue *executes* the \
strategy mechanism on a 1-5 scale.

Definitions (physics framework):
- accumulate: co-directional buildup crossing a threshold — forces stack in \
one direction until a tipping point
- erode: slow wearing-down of support/facade/composure — loss, drain, weakening
- rupture: step function — discontinuous jump, sudden break, hard scene cut
- uncover: cognitive reset — a disclosure invalidates prior understanding
- contest: opposing vectors between characters — active disagreement, refusal, \
coercion, quiet pushback
- drift: Brownian motion — casual banter/atmosphere with no decisive turn
- escalate: continuously raise stakes across multiple beats
- resolve: bring closure and healing to accumulated tension

Scoring rubric:
  5 = textbook execution; a reader would name this strategy without prompting
  4 = clearly executes the mechanism with minor weaknesses
  3 = recognisable but partially confused with an adjacent strategy
  2 = mostly executes a different mechanism, strategy label only loosely fits
  1 = does not exhibit the assigned mechanism at all

Reply in one line: `score=X reason=<≤15 words>`
No preamble, no scoring other fields."""


def _load_run(run_dir: Path) -> VNScript:
    data = json.loads((run_dir / "vn_script.json").read_text(encoding="utf-8"))
    return VNScript.model_validate(data)


def _format_dialogue(scene) -> str:
    lines = []
    for d in scene.dialogue:
        speaker = d.character_id or "NARRATION"
        lines.append(f"[{speaker} | {d.emotion}] {d.text}")
    return "\n".join(lines)


async def _judge_scene(scene, strategy: str) -> tuple[int, str]:
    """Returns (score_int, reason)."""
    try:
        stype = StrategyType(strategy)
        definition = STRATEGIES[stype].description + " — " + STRATEGIES[stype].guidance
    except (ValueError, KeyError):
        definition = f"(no canonical definition for '{strategy}')"

    prompt = (
        f"Strategy assigned: {strategy}\n"
        f"Definition: {definition}\n\n"
        f"Scene dialogue ({len(scene.dialogue)} lines):\n"
        f"{_format_dialogue(scene)}\n\n"
        f"Score this scene's execution of the '{strategy}' mechanism."
    )

    settings = get_settings()
    response = await ainvoke_llm(
        JUDGE_SYSTEM, prompt,
        # Sprint 7-3: judge is its own config field (default Sonnet). Decoupled
        # from reviewer so eval remains rigorous even if pipeline reviewer is
        # swapped for cheaper models.
        model=settings.llm_judge_model,
        caller=f"judge/{scene.id}/{strategy}",
    )
    content = (response.content if hasattr(response, "content") else str(response)).strip()

    # Parse `score=X reason=...`
    import re
    m = re.search(r"score\s*=\s*(\d(?:\.\d)?)", content, re.IGNORECASE)
    score = int(float(m.group(1))) if m else 0
    rm = re.search(r"reason\s*=\s*(.+)", content, re.IGNORECASE)
    reason = rm.group(1).strip().rstrip(".") if rm else content[:80]
    return score, reason


async def _score_run(name: str, script: VNScript) -> list[dict]:
    results = []
    for scene in script.scenes:
        strategy = scene.narrative_strategy or "drift"
        score, reason = await _judge_scene(scene, strategy)
        results.append({
            "scene_id": scene.id,
            "strategy": strategy,
            "score": score,
            "reason": reason,
        })
        print(f"  [{name}] {scene.id:<30} {strategy:<12} score={score}  {reason[:60]}")
    return results


async def main():
    all_results = {}
    for name, path in RUNS.items():
        if not path.exists():
            print(f"Missing run: {path}")
            continue
        print(f"\n== Scoring {name} ({path}) ==")
        script = _load_run(path)
        all_results[name] = await _score_run(name, script)

    print("\n" + "=" * 60)
    print("Aggregate results")
    print("=" * 60)
    for name, rows in all_results.items():
        scores = [r["score"] for r in rows if r["score"] > 0]
        if scores:
            mean = sum(scores) / len(scores)
            print(f"  {name:<10}  n={len(scores)}  mean={mean:.2f}  scores={scores}")

    # Per-strategy breakdown
    print("\nPer-strategy comparison:")
    seen_strategies = set()
    for rows in all_results.values():
        seen_strategies.update(r["strategy"] for r in rows)
    for strat in sorted(seen_strategies):
        parts = []
        for name, rows in all_results.items():
            matches = [r["score"] for r in rows if r["strategy"] == strat and r["score"] > 0]
            if matches:
                parts.append(f"{name}={sum(matches)/len(matches):.1f}(n={len(matches)})")
        if parts:
            print(f"  {strat:<12} {' | '.join(parts)}")

    # Save raw
    out = Path("demo_output/strategy_adherence_eval.json")
    out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRaw scores -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
