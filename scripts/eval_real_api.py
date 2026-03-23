"""Run a real API pipeline and collect token usage data for cost analysis.

Usage: uv run python scripts/eval_real_api.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def main():
    import os
    # Use all-Haiku to stay within rate limits (8K output tokens/min on Sonnet)
    os.environ["LLM_DIRECTOR_MODEL"] = "claude-haiku-4-5-20251001"
    os.environ["LLM_WRITER_MODEL"] = "claude-haiku-4-5-20251001"
    os.environ["LLM_REVIEWER_MODEL"] = "claude-haiku-4-5-20251001"
    os.environ["USE_SEMANTIC_RETRIEVAL"] = "false"

    from vn_agent.agents.graph import build_graph
    from vn_agent.agents.state import initial_state
    from vn_agent.services.token_tracker import tracker
    from vn_agent.observability.tracing import get_trace

    theme = "A lighthouse keeper must decide whether to save a ship or abandon the post during a storm"

    print(f"Running REAL API pipeline (all-Haiku, text_only)...")
    print(f"Theme: {theme}\n")

    graph = build_graph()
    state = initial_state(
        theme=theme,
        output_dir="_eval_real_output",
        text_only=True,   # skip image generation (no OpenAI needed)
        max_scenes=5,
        num_characters=2,
    )

    trace = get_trace()
    result = await graph.ainvoke(state)

    script = result.get("vn_script")
    errors = result.get("errors", [])

    print(f"\n{'='*60}")
    print(f"PIPELINE RESULT")
    print(f"{'='*60}")

    if script:
        print(f"  Title:      {script.title}")
        print(f"  Scenes:     {len(script.scenes)}")
        print(f"  Characters: {len(script.characters)}")
        total_lines = sum(len(s.dialogue) for s in script.scenes)
        print(f"  Dialogue:   {total_lines} lines total")
    else:
        print("  ERROR: No script produced")

    print(f"  Revisions:  {result.get('revision_count', 0)}")
    print(f"  Review:     {'PASS' if result.get('review_passed') else 'FAIL'}")
    if errors:
        print(f"  Errors:     {errors}")

    # Token usage
    print(f"\n{'='*60}")
    print(f"TOKEN USAGE BY AGENT")
    print(f"{'='*60}")
    print(f"  {'Agent':<25} {'Input':>8} {'Output':>8} {'Total':>8}")
    print(f"  {'-'*51}")

    entries = tracker.entries()
    total_input = 0
    total_output = 0

    agent_tokens = {}
    for e in entries:
        agent = e["caller"]
        inp = e["input_tokens"]
        out = e["output_tokens"]
        total_input += inp
        total_output += out
        if agent not in agent_tokens:
            agent_tokens[agent] = {"input": 0, "output": 0}
        agent_tokens[agent]["input"] += inp
        agent_tokens[agent]["output"] += out

    for agent, t in sorted(agent_tokens.items()):
        print(f"  {agent:<25} {t['input']:>8,} {t['output']:>8,} {t['input']+t['output']:>8,}")

    print(f"  {'-'*51}")
    print(f"  {'TOTAL':<25} {total_input:>8,} {total_output:>8,} {total_input+total_output:>8,}")

    # Cost calculation
    # Sonnet 4: Input $3/MTok, Output $15/MTok
    # Haiku 3.5: Input $0.80/MTok, Output $4/MTok
    SONNET_IN, SONNET_OUT = 3.0, 15.0  # $/MTok
    HAIKU_IN, HAIKU_OUT = 0.80, 4.0

    sonnet_agents = {"director/step1", "director/step2", "writer"}
    haiku_agents = {"reviewer", "character_designer", "scene_artist", "eval/strategy"}

    actual_cost = 0.0
    all_sonnet_cost = 0.0

    for agent, t in agent_tokens.items():
        inp, out = t["input"], t["output"]
        # Determine which model this agent used
        is_sonnet = any(s in agent for s in sonnet_agents)
        if is_sonnet:
            actual_cost += inp * SONNET_IN / 1_000_000 + out * SONNET_OUT / 1_000_000
        else:
            actual_cost += inp * HAIKU_IN / 1_000_000 + out * HAIKU_OUT / 1_000_000
        # All-Sonnet baseline
        all_sonnet_cost += inp * SONNET_IN / 1_000_000 + out * SONNET_OUT / 1_000_000

    all_haiku_cost = total_input * HAIKU_IN / 1_000_000 + total_output * HAIKU_OUT / 1_000_000

    print(f"\n{'='*60}")
    print(f"COST ANALYSIS")
    print(f"{'='*60}")
    print(f"  All-Sonnet baseline:      ${all_sonnet_cost:.4f}")
    print(f"  Actual (routed):          ${actual_cost:.4f}  ({(1-actual_cost/all_sonnet_cost)*100:.0f}% savings)" if all_sonnet_cost > 0 else "")
    print(f"  All-Haiku budget mode:    ${all_haiku_cost:.4f}  ({(1-all_haiku_cost/all_sonnet_cost)*100:.0f}% savings)" if all_sonnet_cost > 0 else "")

    # Trace timing
    print(f"\n{'='*60}")
    print(f"TRACE TIMING")
    print(f"{'='*60}")
    for span in trace.spans:
        print(f"  {span.name:<25} {span.duration_s:>6.1f}s  (in={span.attributes.get('input_tokens', 0):,} out={span.attributes.get('output_tokens', 0):,})")

    # Save results
    output = {
        "theme": theme,
        "script_title": script.title if script else None,
        "scenes": len(script.scenes) if script else 0,
        "characters": len(script.characters) if script else 0,
        "total_dialogue_lines": total_lines if script else 0,
        "revision_count": result.get("revision_count", 0),
        "review_passed": result.get("review_passed", False),
        "tokens": {
            "by_agent": agent_tokens,
            "total_input": total_input,
            "total_output": total_output,
        },
        "cost": {
            "all_sonnet": round(all_sonnet_cost, 5),
            "routed": round(actual_cost, 5),
            "all_haiku": round(all_haiku_cost, 5),
            "routing_savings_pct": round((1 - actual_cost / all_sonnet_cost) * 100, 1) if all_sonnet_cost > 0 else 0,
            "budget_savings_pct": round((1 - all_haiku_cost / all_sonnet_cost) * 100, 1) if all_sonnet_cost > 0 else 0,
        },
        "trace": [
            {"name": s.name, "duration_s": round(s.duration_s, 2), "attributes": s.attributes}
            for s in trace.spans
        ],
    }

    out_path = Path("eval_real_api_results.json")
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
