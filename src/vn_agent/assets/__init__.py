"""v4 P0: multi-source material fusion.

Modules:
  text_ingest    — chunk uploaded text (md/pdf/docx) into AnnotatedSession[user_upload]
  upload_store   — persist per-job uploads to disk + load for lore index build
  library        — local open-source asset library (manifest + semantic match)   [P0-2]
  dedup          — cross-source deduplication (pHash + embedding cosine)         [P0-3]
  license_gate   — validate source_license on export                             [P0-4]
  web_search_agent — search-agent orchestrating MCP WebSearch/gemini grounding   [P0-5]

All modules degrade gracefully when the optional `assets` extra is not
installed (pipeline falls back to LLM-only asset generation with a warning).
"""
