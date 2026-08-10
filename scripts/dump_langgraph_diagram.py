"""Dump LangGraph topology as Mermaid (.mmd) and optionally PNG.

Usage:
    PYTHONPATH=src python scripts/dump_langgraph_diagram.py

Outputs:
    docs/v3/pipeline_graph.mmd          — full pipeline (build_graph)
    docs/v3/pipeline_writer_graph.mmd   — resume-from-outline (build_writer_graph)
    docs/v3/pipeline_graph.png          — best-effort, needs mermaid.ink reachable
    docs/v3/pipeline_writer_graph.png

The .mmd files are always written. PNGs require network access to mermaid.ink
(LangGraph's default renderer). If PNG fails, .mmd is still usable — paste into
https://mermaid.live or any markdown viewer that supports mermaid.
"""
from __future__ import annotations

import sys
from pathlib import Path

from vn_agent.agents.graph import build_graph, build_writer_graph

OUT = Path("docs/v3")
OUT.mkdir(parents=True, exist_ok=True)


def dump(app, stem: str) -> None:
    g = app.get_graph()

    mmd_path = OUT / f"{stem}.mmd"
    mmd_path.write_text(g.draw_mermaid(), encoding="utf-8")
    print(f"  wrote {mmd_path}")

    png_path = OUT / f"{stem}.png"
    try:
        png_bytes = g.draw_mermaid_png()
        png_path.write_bytes(png_bytes)
        print(f"  wrote {png_path}")
    except Exception as e:
        print(f"  skipped {png_path} ({type(e).__name__}: {e})")


def main() -> int:
    print("Dumping main pipeline (build_graph)…")
    dump(build_graph(), "pipeline_graph")
    print("Dumping writer-resume pipeline (build_writer_graph)…")
    dump(build_writer_graph(), "pipeline_writer_graph")
    return 0


if __name__ == "__main__":
    sys.exit(main())
