"""v4 P3: Chat Ops — conversational editing of an already-generated VN.

Beyond-workflow interaction: instead of "submit theme, wait for the 6-step
pipeline, download," a creator can address a specific scene/character/asset
in natural language after the initial generation completes. See
`intent_router.py` (classification) and `orchestrator.py` (preview → confirm
→ execute lifecycle, audit trail).
"""
