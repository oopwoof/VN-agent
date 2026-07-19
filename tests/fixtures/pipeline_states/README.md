# Pipeline-state fixtures (v4 P0-resume)

Six directories that simulate on-disk states VN-Agent runs might get stuck at.
Every fixture is a self-contained `output_dir` — same shape as a real
run — so `salvage_run`, CLI `--resume`, and future web-resume endpoints
can be tested end-to-end without spending a token.

| Fixture | State | What it tests |
|---|---|---|
| `post_director/` | Director wrote vn_script + characters; scenes have no dialogue | Salvage should say "noop, no snapshots" |
| `post_writer_partial/` | vn_script.json has 3/5 scenes with dialogue; snapshots/ has all 5 | Salvage overlays snapshots onto empty scenes |
| `post_writer_complete/` | vn_script.json fully populated (5/5 dialogue) | Salvage says "already_complete" |
| `post_writer_no_flush/` | vn_script.json Director-only (0 dialogue); snapshots/ has 5 | Salvage merges snapshots for full recovery |
| `corrupt_vn_script/` | vn_script.json truncated but snapshots present | Salvage raises actionable error |
| `empty/` | Just an empty directory | Salvage raises SalvageError |

Regenerate: `uv run python tests/fixtures/pipeline_states/_regenerate.py`.
The script is idempotent — safe to re-run after schema changes.
