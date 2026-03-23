"""Run all evals with local Ollama model (qwen2.5:7b).

Produces:
1. Strategy classification: LLM F1 vs keyword baseline F1
2. Full pipeline: token counts, timing, structural check, reviewer output
3. Cost comparison data

Usage: uv run python scripts/eval_ollama.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ── Configure for Ollama ──────────────────────────────────────────────────────
os.environ["LLM_PROVIDER"] = "openai"
os.environ["LLM_MODEL"] = "qwen2.5:7b"
os.environ["LLM_BASE_URL"] = "http://localhost:11434/v1"
os.environ["LLM_API_KEY"] = "ollama"
os.environ["OPENAI_API_KEY"] = "ollama"  # override .env to prevent auth errors
os.environ["LLM_MAX_TOKENS"] = "4096"
os.environ["LLM_TEMPERATURE"] = "0.3"
# All agents use the same local model
os.environ["LLM_DIRECTOR_MODEL"] = "qwen2.5:7b"
os.environ["LLM_WRITER_MODEL"] = "qwen2.5:7b"
os.environ["LLM_REVIEWER_MODEL"] = "qwen2.5:7b"
os.environ["LLM_CHARACTER_DESIGNER_MODEL"] = "qwen2.5:7b"
os.environ["LLM_SCENE_ARTIST_MODEL"] = "qwen2.5:7b"
os.environ["LLM_MUSIC_DIRECTOR_MODEL"] = "qwen2.5:7b"
# Disable embedding RAG to keep it simple
os.environ["USE_SEMANTIC_RETRIEVAL"] = "false"
# Disable tool calling (Ollama qwen2.5 doesn't support function calling well)
os.environ["USE_TOOL_CALLING"] = "false"

# IMPORTANT: bypass settings.yaml which passes constructor kwargs that override env vars
import vn_agent.config
vn_agent.config._load_yaml_settings = lambda: {}
vn_agent.config.get_settings.cache_clear()


async def run_strategy_eval(sample_size: int = 100) -> dict:
    """Run strategy classification eval: keyword baseline vs LLM."""
    from vn_agent.eval.corpus import load_corpus
    from vn_agent.eval.strategy_eval import (
        evaluate_strategy_classification,
        format_report,
        keyword_classifier,
    )
    from vn_agent.services.llm import ainvoke_llm

    corpus_path = Path("data/final_annotations.csv")
    if not corpus_path.exists():
        print("  [SKIP] Corpus not found")
        return {}

    sessions = load_corpus(corpus_path)
    print(f"  Loaded {len(sessions)} sessions")

    # Keyword baseline
    print(f"  Running keyword baseline ({sample_size} samples)...")

    async def kw_classifier(text: str) -> str:
        return keyword_classifier(text)

    kw_metrics = await evaluate_strategy_classification(sessions, kw_classifier, sample_size)
    print(f"  Keyword: accuracy={kw_metrics['accuracy']:.1%}, macro_f1={_macro_f1(kw_metrics):.3f}")

    # LLM classifier
    print(f"  Running LLM classifier ({sample_size} samples, ~{sample_size * 2}s estimated)...")

    async def llm_classifier(text: str) -> str:
        response = await ainvoke_llm(
            "You are a narrative strategy classifier for visual novel dialogues. "
            "Classify the predominant narrative strategy as exactly one of: "
            "accumulate, erode, rupture, reveal, contrast, weave. "
            "Respond with ONLY the strategy name, nothing else.",
            f"Classify this dialogue:\n\n{text[:1500]}",
            caller="eval/strategy",
        )
        content = response.content if hasattr(response, "content") else str(response)
        return content.strip().lower()

    t0 = time.time()
    llm_metrics = await evaluate_strategy_classification(sessions, llm_classifier, sample_size)
    elapsed = time.time() - t0
    print(f"  LLM: accuracy={llm_metrics['accuracy']:.1%}, macro_f1={_macro_f1(llm_metrics):.3f} ({elapsed:.0f}s)")

    return {
        "sample_size": sample_size,
        "keyword": {"accuracy": kw_metrics["accuracy"], "macro_f1": _macro_f1(kw_metrics), "per_class": kw_metrics.get("per_class", {})},
        "llm": {"accuracy": llm_metrics["accuracy"], "macro_f1": _macro_f1(llm_metrics), "per_class": llm_metrics.get("per_class", {}), "time_s": round(elapsed, 1)},
    }


async def run_pipeline() -> dict:
    """Run full pipeline and collect metrics."""
    from vn_agent.agents.graph import build_graph
    from vn_agent.agents.reviewer import _structural_check
    from vn_agent.agents.state import initial_state
    from vn_agent.observability.tracing import get_trace
    from vn_agent.services.token_tracker import tracker

    theme = "A lighthouse keeper must choose between saving a ship or abandoning the post"
    print(f"  Theme: {theme}")

    graph = build_graph()
    state = initial_state(
        theme=theme,
        output_dir="_eval_ollama_output",
        text_only=True,
        max_scenes=4,
        num_characters=2,
    )

    trace = get_trace()
    t0 = time.time()

    try:
        result = await graph.ainvoke(state)
    except Exception as e:
        return {"error": str(e), "time_s": round(time.time() - t0, 1)}

    elapsed = time.time() - t0
    script = result.get("vn_script")

    data = {
        "time_s": round(elapsed, 1),
        "revision_count": result.get("revision_count", 0),
        "review_passed": result.get("review_passed", False),
        "errors": result.get("errors", []),
    }

    if script:
        structural = _structural_check(script)
        total_lines = sum(len(s.dialogue) for s in script.scenes)
        data.update({
            "title": script.title,
            "scenes": len(script.scenes),
            "characters": len(script.characters),
            "dialogue_lines": total_lines,
            "structural_passed": structural.passed,
            "structural_issues": structural.issues,
        })

    # Token usage
    agent_tokens = {}
    for c in tracker.calls:
        if c.caller not in agent_tokens:
            agent_tokens[c.caller] = {"input": 0, "output": 0}
        agent_tokens[c.caller]["input"] += c.input_tokens
        agent_tokens[c.caller]["output"] += c.output_tokens

    total_in = sum(t["input"] for t in agent_tokens.values())
    total_out = sum(t["output"] for t in agent_tokens.values())
    data["tokens"] = {"by_agent": agent_tokens, "total_input": total_in, "total_output": total_out}

    # Trace spans
    data["trace"] = [
        {"name": s.name, "duration_s": round(s.duration_s, 1)}
        for s in trace.spans
    ]

    return data


def _macro_f1(metrics: dict) -> float:
    per_class = metrics.get("per_class", {})
    if not per_class:
        return 0.0
    f1s = [v["f1"] for v in per_class.values()]
    return round(sum(f1s) / len(f1s), 4) if f1s else 0.0


async def main():
    print("=" * 60)
    print("VN-Agent Evaluation Suite (Ollama qwen2.5:7b)")
    print("=" * 60)

    all_results = {}

    # ── 1. Strategy Classification ────────────────────────────
    print("\n[1/2] Strategy Classification Eval")
    print("-" * 40)
    strat_results = await run_strategy_eval(sample_size=100)
    all_results["strategy_eval"] = strat_results

    if strat_results and "llm" in strat_results:
        kw_f1 = strat_results["keyword"]["macro_f1"]
        llm_f1 = strat_results["llm"]["macro_f1"]
        improvement = (llm_f1 - kw_f1) / kw_f1 * 100 if kw_f1 > 0 else 0
        print(f"\n  >> Keyword F1: {kw_f1:.3f} → LLM F1: {llm_f1:.3f} ({improvement:+.0f}%)")

    # ── 2. Full Pipeline ──────────────────────────────────────
    print("\n[2/2] Full Pipeline Run")
    print("-" * 40)
    pipe_results = await run_pipeline()
    all_results["pipeline"] = pipe_results

    if "error" not in pipe_results:
        print(f"\n  >> {pipe_results.get('scenes', 0)} scenes, "
              f"{pipe_results.get('dialogue_lines', 0)} lines, "
              f"structural={'PASS' if pipe_results.get('structural_passed') else 'FAIL'}, "
              f"{pipe_results.get('time_s', 0)}s total")
        print(f"  >> Tokens: in={pipe_results['tokens']['total_input']:,} out={pipe_results['tokens']['total_output']:,}")
        if pipe_results.get("trace"):
            print(f"  >> Per-node timing:")
            for s in pipe_results["trace"]:
                print(f"     {s['name']:<25} {s['duration_s']:>6.1f}s")
    else:
        print(f"\n  >> ERROR: {pipe_results['error']}")

    # ── Save ──────────────────────────────────────────────────
    out_path = Path("eval_ollama_results.json")
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"\n{'='*60}")
    print(f"All results saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
