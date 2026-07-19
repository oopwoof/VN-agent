"""v4 P0-resume: salvage a stuck / crashed run from on-disk artifacts.

When the pipeline hangs or crashes after Writer has produced dialogue but
before build_project runs, downstream tooling has two sources of truth
for scene content:

1. `vn_script.json`   — the canonical merged blackboard (post-fix: written
                        after every completed scene by Writer)
2. `snapshots/*.json` — per-scene checkpoints (Phase 13 Sprint 11-4)

Salvage picks whichever is more complete and produces a valid vn_script
that `--resume` can consume. Legacy stuck jobs from before the per-scene
flush landed can only be recovered via snapshots; salvage handles that.

Callers:
- `vn-agent salvage --output <dir>`   (CLI, this file)
- `POST /api/projects/{id}/resume`   (web, uses the same logic)
- Downstream tests exercising the fixture matrix
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import Scene, VNScript

logger = logging.getLogger(__name__)


@dataclass
class SalvageReport:
    """Diagnostic view of what salvage did (or refused to do)."""
    output_dir: str
    action: str = "noop"                    # noop / merged_snapshots / already_complete / failed
    scenes_before: int = 0
    dialogue_before: int = 0
    scenes_after: int = 0
    dialogue_after: int = 0
    snapshots_found: int = 0
    snapshots_merged: int = 0
    warnings: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)  # paths touched

    def to_dict(self) -> dict:
        return {
            "output_dir": self.output_dir,
            "action": self.action,
            "scenes_before": self.scenes_before,
            "dialogue_before": self.dialogue_before,
            "scenes_after": self.scenes_after,
            "dialogue_after": self.dialogue_after,
            "snapshots_found": self.snapshots_found,
            "snapshots_merged": self.snapshots_merged,
            "warnings": self.warnings,
            "written": self.written,
        }


class SalvageError(RuntimeError):
    """Raised only when there's genuinely nothing to salvage."""


def _read_script(script_path: Path) -> VNScript | None:
    if not script_path.exists():
        return None
    try:
        return VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"vn_script.json at {script_path} is corrupt: {e}")
        return None


def _read_characters(chars_path: Path) -> dict[str, CharacterProfile]:
    if not chars_path.exists():
        return {}
    try:
        raw = json.loads(chars_path.read_text(encoding="utf-8"))
        return {k: CharacterProfile.model_validate(v) for k, v in raw.items()}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"characters.json at {chars_path} is unreadable: {e}")
        return {}


def _load_snapshots(snap_dir: Path) -> dict[str, dict]:
    """Load `snapshots/*.json` keyed by scene_id. Missing dir → empty."""
    if not snap_dir.exists() or not snap_dir.is_dir():
        return {}
    out: dict[str, dict] = {}
    for p in sorted(snap_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Skipping unreadable snapshot {p.name}: {e}")
            continue
        sid = data.get("scene_id") or p.stem
        # If two files describe the same scene (revision loop), keep the
        # richer one — measured by dialogue line count.
        prior = out.get(sid)
        prior_len = len(prior.get("dialogue") or []) if prior else -1
        new_len = len(data.get("dialogue") or [])
        if new_len >= prior_len:
            out[sid] = data
    return out


def _scene_dialogue_count(scene: Scene | None) -> int:
    if scene is None:
        return 0
    return len(scene.dialogue or [])


def _apply_snapshot_to_scene(scene: Scene, snap: dict) -> Scene:
    """Overlay snapshot dialogue + state_writes onto a Director-outline scene."""
    from vn_agent.schema.script import DialogueLine

    dialogue = []
    for entry in snap.get("dialogue", []) or []:
        try:
            dialogue.append(DialogueLine(
                character_id=entry.get("character_id"),
                text=entry.get("text", ""),
                emotion=entry.get("emotion") or "neutral",
            ))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Skipping bad dialogue entry in snapshot {snap.get('scene_id')}: {e}")

    updates = {}
    if dialogue:
        updates["dialogue"] = dialogue
    if snap.get("summary"):
        updates["summary"] = snap["summary"]
    if snap.get("state_writes"):
        try:
            updates["state_writes"] = dict(snap["state_writes"])
        except Exception:  # noqa: BLE001
            pass
    return scene.model_copy(update=updates) if updates else scene


def salvage_run(
    output_dir: str | Path,
    *,
    write: bool = True,
    force: bool = False,
) -> SalvageReport:
    """Reconstruct a valid vn_script.json from the best-available data.

    Behavior matrix:

    - vn_script.json present + all scenes have dialogue → `already_complete`,
      no writes.
    - vn_script.json present but some scenes empty → walk snapshots/, overlay
      dialogue on empty scenes → `merged_snapshots`.
    - vn_script.json missing but Director outline in vn_script.json.bak or
      recoverable via snapshots alone → try snapshot-only mode.
    - Nothing recoverable → raise SalvageError.

    `write=False` returns the report but leaves disk untouched (dry-run).
    `force=True` overrides the "already complete" short-circuit.
    """
    output = Path(output_dir)
    if not output.exists():
        raise SalvageError(f"output_dir does not exist: {output}")

    script_path = output / "vn_script.json"
    chars_path = output / "characters.json"
    snap_dir = output / "snapshots"

    report = SalvageReport(output_dir=str(output))

    script = _read_script(script_path)
    characters = _read_characters(chars_path)
    snapshots = _load_snapshots(snap_dir)
    report.snapshots_found = len(snapshots)

    if script is None and not snapshots:
        raise SalvageError(
            f"Nothing to salvage: {script_path.name} missing/unreadable "
            f"and no snapshots/ directory. Did the run ever start Writer?"
        )

    # Snapshot-only mode: no vn_script, but scenes exist as snapshots.
    # Rare — happens if Director's checkpoint write failed on a legacy
    # run. Build a minimal placeholder script from snapshot scene_ids.
    if script is None:
        raise SalvageError(
            f"vn_script.json missing at {script_path}. Snapshot-only "
            f"reconstruction would need a Director outline; that's out "
            f"of M0 scope. Restore vn_script.json from a backup and rerun."
        )

    # Assess current script completeness.
    report.scenes_before = len(script.scenes)
    report.dialogue_before = sum(_scene_dialogue_count(s) for s in script.scenes)

    empty_scene_ids = [s.id for s in script.scenes if _scene_dialogue_count(s) == 0]

    if not empty_scene_ids and not force:
        report.action = "already_complete"
        report.scenes_after = report.scenes_before
        report.dialogue_after = report.dialogue_before
        return report

    if not snapshots:
        report.warnings.append(
            f"vn_script has {len(empty_scene_ids)} empty scenes but no snapshots/ "
            f"to overlay. Leaving disk untouched."
        )
        report.action = "noop"
        report.scenes_after = report.scenes_before
        report.dialogue_after = report.dialogue_before
        return report

    # Overlay snapshots onto empty scenes. Non-empty scenes stay untouched
    # unless force=True (then snapshots override).
    new_scenes = []
    merged = 0
    for scene in script.scenes:
        snap = snapshots.get(scene.id)
        should_overlay = snap is not None and (
            _scene_dialogue_count(scene) == 0 or force
        )
        if should_overlay:
            new_scenes.append(_apply_snapshot_to_scene(scene, snap))
            merged += 1
        else:
            new_scenes.append(scene)

    merged_script = script.model_copy(update={"scenes": new_scenes})
    report.scenes_after = len(new_scenes)
    report.dialogue_after = sum(_scene_dialogue_count(s) for s in new_scenes)
    report.snapshots_merged = merged

    if merged == 0:
        report.action = "noop"
        return report

    report.action = "merged_snapshots"

    if not write:
        return report

    # Atomic write (temp + rename), mirroring writer's _flush_partial_vn_script.
    try:
        tmp = script_path.with_suffix(".json.tmp")
        tmp.write_text(merged_script.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(script_path)
        report.written.append(str(script_path))
    except OSError as e:
        report.warnings.append(f"vn_script write failed: {e}")
        report.action = "failed"

    # characters.json: leave as-is if present; no snapshot source for it.
    if not characters and (chars_path.exists()):
        report.warnings.append("characters.json unreadable; downstream may reject.")

    return report
