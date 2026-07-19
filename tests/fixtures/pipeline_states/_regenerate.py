"""Regenerate the pipeline-state fixture set used by test_resume_flow.py.

Idempotent; safe to re-run after schema changes. See README.md in this
directory for the fixture matrix.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import DialogueLine, Scene, VNScript

_HERE = Path(__file__).resolve().parent


# ── Base blackboard (Director step ~ 5-scene school-life demo) ──────────────

_CHARS = {
    "alice": CharacterProfile(
        id="alice", name="Alice", role="protagonist",
        personality="curious, gentle", background="new transfer student",
        color="#ff8fa0",
    ),
    "bob": CharacterProfile(
        id="bob", name="Bob", role="friend",
        personality="loyal, playful", background="alice's classmate",
        color="#7aa2ff",
    ),
}

_SCENE_SKELETON: list[tuple[str, str, str]] = [
    ("scene_1_arrival", "The Arrival", "Alice enters the school gate for the first time."),
    ("scene_2_meeting", "Meeting Bob", "Alice and Bob meet during morning cleaning."),
    ("scene_3_lunch",   "Lunch Talk",  "The two share bento and swap stories."),
    ("scene_4_choice",  "The Choice",  "Alice must decide whether to join Bob's club."),
    ("scene_5_dusk",    "Rooftop Dusk", "They watch the sun set together, questions unresolved."),
]

def _build_base_script(with_dialogue_for: set[str] | None = None) -> VNScript:
    """Return a 5-scene VNScript. `with_dialogue_for` selects scene ids
    that should carry dialogue; the rest stay empty (Director-only)."""
    with_dialogue_for = with_dialogue_for or set()

    scenes: list[Scene] = []
    for i, (sid, title, desc) in enumerate(_SCENE_SKELETON):
        dialogue: list[DialogueLine] = []
        if sid in with_dialogue_for:
            dialogue = [
                DialogueLine(character_id="alice", text=f"{title}: opening line.", emotion="neutral"),
                DialogueLine(character_id="bob",   text=f"{title}: reply.",         emotion="happy"),
                DialogueLine(character_id="alice", text=f"{title}: reflection.",    emotion="thoughtful"),
            ]
        scenes.append(Scene(
            id=sid,
            title=title,
            description=desc,
            background_id="bg_school_day" if i < 3 else "bg_rooftop_night",
            characters_present=["alice", "bob"],
            dialogue=dialogue,
        ))

    return VNScript(
        title="A Quiet Semester",
        theme="school life, gentle friendship",
        description="A tiny 5-scene fixture used for resume/salvage tests.",
        start_scene_id="scene_1_arrival",
        scenes=scenes,
    )


def _snapshot_payload(sid: str, title: str) -> dict:
    """Match writer._write_scene_snapshot's shape."""
    return {
        "scene_id": sid,
        "title": title,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dialogue": [
            {"character_id": "alice", "text": f"{title}: opening line.",  "emotion": "neutral"},
            {"character_id": "bob",   "text": f"{title}: reply.",         "emotion": "happy"},
            {"character_id": "alice", "text": f"{title}: reflection.",    "emotion": "thoughtful"},
        ],
        "narrative_strategy": "accumulate",
        "state_reads": [],
        "state_writes": {},
        "world_state_after": {},
        "summary": f"Salvage-fixture summary for {sid}.",
    }


def _clean(dir_: Path) -> Path:
    if dir_.exists():
        shutil.rmtree(dir_)
    dir_.mkdir(parents=True)
    return dir_


def _write_script(dir_: Path, script: VNScript) -> None:
    (dir_ / "vn_script.json").write_text(
        script.model_dump_json(indent=2), encoding="utf-8",
    )


def _write_characters(dir_: Path) -> None:
    chars = {k: v.model_dump() for k, v in _CHARS.items()}
    (dir_ / "characters.json").write_text(
        json.dumps(chars, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def _write_snapshots(dir_: Path, scene_ids: list[str]) -> None:
    snap_dir = dir_ / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    title_map = {sid: title for sid, title, _ in _SCENE_SKELETON}
    for sid in scene_ids:
        (snap_dir / f"{sid}.json").write_text(
            json.dumps(_snapshot_payload(sid, title_map[sid]), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_all() -> None:
    all_ids = [sid for sid, _, _ in _SCENE_SKELETON]

    # 1. post_director — outline only, no snapshots
    d = _clean(_HERE / "post_director")
    _write_script(d, _build_base_script())
    _write_characters(d)

    # 2. post_writer_partial — 3/5 in vn_script; all 5 in snapshots/
    d = _clean(_HERE / "post_writer_partial")
    _write_script(d, _build_base_script(with_dialogue_for=set(all_ids[:3])))
    _write_characters(d)
    _write_snapshots(d, all_ids)

    # 3. post_writer_complete — 5/5 in vn_script; snapshots present too
    d = _clean(_HERE / "post_writer_complete")
    _write_script(d, _build_base_script(with_dialogue_for=set(all_ids)))
    _write_characters(d)
    _write_snapshots(d, all_ids)

    # 4. post_writer_no_flush — vn_script has ZERO dialogue but snapshots
    # cover all 5 scenes. Legacy behavior before per-scene flush landed.
    d = _clean(_HERE / "post_writer_no_flush")
    _write_script(d, _build_base_script())
    _write_characters(d)
    _write_snapshots(d, all_ids)

    # 5. corrupt_vn_script — truncated JSON; snapshots survive.
    d = _clean(_HERE / "corrupt_vn_script")
    (d / "vn_script.json").write_text('{"title": "broken"', encoding="utf-8")
    _write_characters(d)
    _write_snapshots(d, all_ids)

    # 6. empty — a bare directory. Salvage should refuse.
    _clean(_HERE / "empty")

    print(f"Regenerated fixtures at {_HERE}")


if __name__ == "__main__":
    build_all()
