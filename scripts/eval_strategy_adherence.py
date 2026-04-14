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
import os
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


def _build_judge_prompt(scene, strategy: str) -> str:
    try:
        stype = StrategyType(strategy)
        definition = STRATEGIES[stype].description + " — " + STRATEGIES[stype].guidance
    except (ValueError, KeyError):
        definition = f"(no canonical definition for '{strategy}')"
    return (
        f"Strategy assigned: {strategy}\n"
        f"Definition: {definition}\n\n"
        f"Scene dialogue ({len(scene.dialogue)} lines):\n"
        f"{_format_dialogue(scene)}\n\n"
        f"Score this scene's execution of the '{strategy}' mechanism."
    )


def _parse_judge_output(content: str) -> tuple[int, str]:
    import re
    content = content.strip()
    m = re.search(r"score\s*=\s*(\d(?:\.\d)?)", content, re.IGNORECASE)
    score = int(float(m.group(1))) if m else 0
    rm = re.search(r"reason\s*=\s*(.+)", content, re.IGNORECASE)
    reason = rm.group(1).strip().rstrip(".") if rm else content[:80]
    return score, reason


async def _judge_with_model(scene, strategy: str, model: str) -> tuple[int, str]:
    """Runs one judge call against the specified model."""
    prompt = _build_judge_prompt(scene, strategy)
    response = await ainvoke_llm(
        JUDGE_SYSTEM, prompt,
        model=model,
        caller=f"judge/{scene.id}/{strategy}/{model.split('-')[0]}",
    )
    content = response.content if hasattr(response, "content") else str(response)
    return _parse_judge_output(content)


async def _judge_scene(scene, strategy: str) -> dict:
    """Returns dict with primary (Sonnet) + optional secondary (GPT-4o) scores.

    Sprint 8-1: cross-model judging defuses the echo-chamber critique
    that "the Sonnet judge grades Sonnet's own output." Pearson
    correlation across judges is reported in the aggregate.

    Gracefully degrades to Sonnet-only when OPENAI_API_KEY is missing
    or llm_judge_model_secondary is empty.
    """
    settings = get_settings()

    primary_score, primary_reason = await _judge_with_model(
        scene, strategy, settings.llm_judge_model,
    )
    result = {
        "score_primary": primary_score,
        "reason_primary": primary_reason,
        "judge_primary": settings.llm_judge_model,
    }

    # Secondary judge (cross-model sanity)
    secondary = settings.llm_judge_model_secondary
    if secondary and (settings.openai_api_key or os.environ.get("OPENAI_API_KEY")):
        try:
            sec_score, sec_reason = await _judge_with_model(scene, strategy, secondary)
            result.update({
                "score_secondary": sec_score,
                "reason_secondary": sec_reason,
                "judge_secondary": secondary,
                "delta": abs(primary_score - sec_score) if sec_score > 0 else None,
            })
        except Exception as e:
            # Don't fail the whole eval if secondary judge is unreachable
            print(f"  [warn] secondary judge ({secondary}) failed for {scene.id}: {e}")
            result["secondary_error"] = str(e)[:120]
    else:
        result["secondary_skipped"] = "no OPENAI_API_KEY or llm_judge_model_secondary unset"

    return result


async def _score_run(name: str, script: VNScript) -> list[dict]:
    results = []
    for scene in script.scenes:
        strategy = scene.narrative_strategy or "drift"
        judged = await _judge_scene(scene, strategy)
        row = {
            "scene_id": scene.id,
            "strategy": strategy,
            # Backwards compat: "score" / "reason" = primary judge so older
            # callers still work
            "score": judged.get("score_primary", 0),
            "reason": judged.get("reason_primary", ""),
            **judged,
        }
        results.append(row)
        sec = judged.get("score_secondary")
        sec_str = f" sec={sec}" if sec is not None else ""
        print(
            f"  [{name}] {scene.id:<30} {strategy:<12} "
            f"primary={row['score']}{sec_str}  {row['reason'][:50]}"
        )
    return results


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Simple Pearson correlation; returns None when undefined (n<2 or zero var)."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


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
    print("Aggregate results (primary judge)")
    print("=" * 60)
    for name, rows in all_results.items():
        scores = [r["score"] for r in rows if r["score"] > 0]
        if scores:
            mean = sum(scores) / len(scores)
            print(f"  {name:<10}  n={len(scores)}  mean={mean:.2f}  scores={scores}")

    # Sprint 8-1: cross-model agreement — inter-rater reliability
    primaries: list[float] = []
    secondaries: list[float] = []
    secondary_present = False
    for rows in all_results.values():
        for r in rows:
            p = r.get("score_primary", 0)
            s = r.get("score_secondary")
            if p > 0 and s is not None and s > 0:
                primaries.append(float(p))
                secondaries.append(float(s))
                secondary_present = True

    if secondary_present:
        r_val = _pearson(primaries, secondaries)
        agreement = sum(1 for p, s in zip(primaries, secondaries) if abs(p - s) <= 1) / len(primaries)
        mean_p = sum(primaries) / len(primaries)
        mean_s = sum(secondaries) / len(secondaries)
        print("\nCross-model judge agreement (Sprint 8-1):")
        print(f"  n_pairs   = {len(primaries)}")
        print(f"  mean_primary   = {mean_p:.2f}  ({rows[0].get('judge_primary','?')})")
        print(f"  mean_secondary = {mean_s:.2f}  ({rows[0].get('judge_secondary','?')})")
        print(f"  Pearson r      = {r_val:.3f}" if r_val is not None else "  Pearson r      = undefined")
        print(f"  ±1-point agreement = {agreement:.0%}")
        if r_val is not None and r_val < 0.3:
            print("  [WARN] low cross-model correlation — primary judge may be biased")
        elif r_val is not None and r_val > 0.7:
            print("  [OK] judges broadly agree — primary scores credible")
    else:
        print("\n(Secondary judge skipped — no OPENAI_API_KEY or config disabled)")

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
