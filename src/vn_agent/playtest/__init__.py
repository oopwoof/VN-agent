"""P4 M0: PlaytestAgent + Vision LLM Judge.

Post-generation, opt-in "health check" for a compiled VN project. Walks the
script's branch graph, composites a representative visual frame per scene/
choice-menu node (Pillow — no Ren'Py engine execution, see
`frame_compositor.py` docstring for why), sends each frame to a vision LLM
judge, and writes a report to `<output_dir>/playtest/report.json`.

M0 scope: report-only. Nothing here writes back into `AgentState`, triggers
a Director/Writer revision, or is wired into `agents/graph.py` as a pipeline
node — this is a manual, opt-in post-processing step (CLI + web endpoint)
run against a project that already exists on disk.
"""
