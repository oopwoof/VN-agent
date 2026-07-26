"""v4 P5 M0: Autopilot — theme -> one hand-picked preset -> playable VN.

Modules:
  resolver   — preset loading + per-job Settings override construction
  outcomes   — append-only JSONL run-outcome log (data/autopilot/runs.jsonl)

M0 boundary: `resolver.resolve_preset()` always returns "autopilot_best" —
no per-theme/tag-based selection yet. `outcomes` is captured but not
consumed; M1 ranks presets by completion rate + P4 Vision Judge score once
enough runs have accumulated (see docs/v4/PRODUCT_v4.md P5 section).
"""
