"""v4 P1: creator feedback flywheel (data → BM25 few-shot → Reflection meta-rules).

Modules:
  store         — JSONL persistence for 👍/👎 records
  injector      — BM25 lookup + Writer prompt few-shot injection      [P1-2]
  reflection    — Haiku batch job → dynamic_guidelines.json           [P1-3]

M0 boundary: no DPO fine-tune. That's M2+ and needs ≥1000 records first
(see docs/v4/PRODUCT_v4.md §5.6 · B, and the盲点 tracking table).
"""
