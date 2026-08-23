"""Chat-ops intent executors.

One module per mutating intent. `orchestrator._HANDLERS` maps an intent
name to the `execute(output_dir, preview)` coroutine here; the
orchestrator owns the preview/confirm/audit lifecycle and knows nothing
about how an individual intent does its work.
"""
