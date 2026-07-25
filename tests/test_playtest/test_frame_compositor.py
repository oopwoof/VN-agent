"""P4: frame_compositor.composite_frame — pure Pillow, no LLM, no network.
Uses the `post_writer_complete` fixture (real dialogue/background/character
variety — this fixture has no wired branch graph, which is irrelevant here;
the compositor only needs one Scene + WalkNode at a time) run through the
real `compiler.project_builder.build_project()` so placeholder PNGs exist
on disk exactly as they would for a real job."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from vn_agent.compiler.project_builder import build_project
from vn_agent.playtest.branch_walker import walk_script
from vn_agent.playtest.frame_compositor import CANVAS_SIZE, composite_frame
from vn_agent.playtest.schema import WalkNode
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pipeline_states"


def _load_project(tmp_path: Path) -> tuple[VNScript, dict[str, CharacterProfile], Path]:
    src = _FIXTURES / "post_writer_complete"
    script = VNScript.model_validate_json((src / "vn_script.json").read_text(encoding="utf-8"))
    raw_chars = json.loads((src / "characters.json").read_text(encoding="utf-8"))
    characters = {k: CharacterProfile.model_validate(v) for k, v in raw_chars.items()}
    project_dir = tmp_path / "proj"
    build_project(script, characters, project_dir)
    return script, characters, project_dir


def test_composite_scene_frame_produces_valid_png(tmp_path):
    script, characters, project_dir = _load_project(tmp_path)
    scene = script.scenes[0]
    node = WalkNode(
        node_id=scene.id, scene_id=scene.id, scene_title=scene.title, kind="scene",
        dialogue_excerpt=["alice (neutral): hi"],
    )

    frame_path = composite_frame(node, scene, characters, project_dir, project_dir)

    assert frame_path.exists()
    img = Image.open(frame_path)
    img.verify()
    img = Image.open(frame_path)  # re-open: verify() invalidates the handle
    assert img.size == CANVAS_SIZE


def test_composite_frame_missing_background_falls_back_without_exception(tmp_path):
    script, characters, project_dir = _load_project(tmp_path)
    scene = script.scenes[0]
    bg_path = project_dir / "game" / "images" / "backgrounds" / f"{scene.background_id}.png"
    bg_path.unlink()

    node = WalkNode(node_id=scene.id, scene_id=scene.id, scene_title=scene.title, kind="scene")
    frame_path = composite_frame(node, scene, characters, project_dir, project_dir)

    assert frame_path.exists()
    Image.open(frame_path).verify()


def test_composite_choice_menu_frame_with_locked_option(tmp_path):
    script, characters, project_dir = _load_project(tmp_path)
    scene = script.scenes[0]
    node = WalkNode(
        node_id=f"{scene.id}::choice", scene_id=scene.id, scene_title=scene.title,
        kind="choice_menu", choice_texts=["Say hi"], locked_choice_texts=["Secret option"],
    )

    frame_path = composite_frame(node, scene, characters, project_dir, project_dir)

    assert frame_path.exists()
    Image.open(frame_path).verify()


def test_composite_frame_walk_plan_integration(tmp_path):
    """Sanity check the two modules compose: walk_script's own WalkNodes can
    be fed straight into composite_frame without adaptation."""
    script, characters, project_dir = _load_project(tmp_path)
    plan = walk_script(script)
    scene_map = {s.id: s for s in script.scenes}

    for node in plan.nodes[:3]:
        scene = scene_map[node.scene_id]
        frame_path = composite_frame(node, scene, characters, project_dir, project_dir)
        assert frame_path.exists()
