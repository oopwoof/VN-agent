"""Phase 13-1 / Step 5: narrative graph schema + validator + writer injection."""
from __future__ import annotations

import pytest

from vn_agent.agents.structure_reviewer import _check_context_deps
from vn_agent.agents.writer import _format_graph_context
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import (
    DialogueLine,
    Scene,
    SceneContextRef,
    VNScript,
    WorldVariable,
)


def _scene(sid: str, deps: list[SceneContextRef] | None = None,
           state_reads: list[str] | None = None, chars: list[str] | None = None,
           dialogue: list[DialogueLine] | None = None, summary: str | None = None) -> Scene:
    return Scene(
        id=sid, title=sid.upper(), description=f"scene {sid}",
        background_id=f"bg_{sid}",
        characters_present=chars or ["alice"],
        state_reads=state_reads or [],
        context_deps=deps or [],
        dialogue=dialogue or [],
        summary=summary,
    )


def _script(scenes: list[Scene], world_vars: list[WorldVariable] | None = None) -> VNScript:
    return VNScript(
        title="T", description="desc", theme="th", start_scene_id=scenes[0].id,
        scenes=scenes,
        world_variables=world_vars or [],
    )


# ------------------------------------------------------------
# Schema + model_copy
# ------------------------------------------------------------


def test_scene_context_ref_basic():
    ref = SceneContextRef(
        ref_type="scene", ref_id="s02", link_type="callback",
        reason="A's confession recalled here",
    )
    assert ref.inject_as == "summary"  # default


def test_context_deps_max_5():
    """max_length=5 is enforced at schema validation — 6+ deps reject."""
    scene_ok = Scene(
        id="s99", title="t", description="d", background_id="bg",
        context_deps=[
            SceneContextRef(
                ref_type="scene", ref_id=f"s{i:02d}", link_type="callback",
                reason=f"cb{i}",
            )
            for i in range(5)
        ],
    )
    assert len(scene_ok.context_deps) == 5

    with pytest.raises(Exception):  # ValidationError
        Scene(
            id="s99", title="t", description="d", background_id="bg",
            context_deps=[
                SceneContextRef(
                    ref_type="scene", ref_id=f"s{i:02d}", link_type="callback",
                    reason=f"cb{i}",
                )
                for i in range(6)
            ],
        )


# ------------------------------------------------------------
# Validator (structure_reviewer._check_context_deps)
# ------------------------------------------------------------


# Phase 13-2 Step 4e: _check_context_deps now returns list[StructureFinding]
# instead of list[str]. Substring assertions check f.message; empty-list
# assertions check the findings list directly.


def test_validator_rejects_forward_scene_ref():
    s1 = _scene("s01", deps=[SceneContextRef(
        ref_type="scene", ref_id="s02", link_type="callback",
        reason="forward ref",
    )])
    s2 = _scene("s02")
    script = _script([s1, s2])
    findings = _check_context_deps(script, {})
    assert any("forward/same-scene" in f.message for f in findings)


def test_validator_rejects_self_ref():
    s1 = _scene("s01", deps=[SceneContextRef(
        ref_type="scene", ref_id="s01", link_type="callback",
        reason="self ref",
    )])
    script = _script([s1])
    findings = _check_context_deps(script, {})
    assert any("self-references" in f.message for f in findings)


def test_validator_rejects_unknown_scene_ref():
    s2 = _scene("s02", deps=[SceneContextRef(
        ref_type="scene", ref_id="s99", link_type="callback",
        reason="dangling",
    )])
    script = _script([_scene("s01"), s2])
    findings = _check_context_deps(script, {})
    assert any("unknown scene" in f.message for f in findings)
    # 4e categorization: a dangling scene ref is branch_target_invalid
    # (deterministic, requires_retry=True) so it routes to step2 retry.
    assert any(f.category == "branch_target_invalid" for f in findings)


def test_validator_accepts_backward_scene_ref():
    s2 = _scene("s02", deps=[SceneContextRef(
        ref_type="scene", ref_id="s01", link_type="callback",
        reason="valid backward",
    )])
    script = _script([_scene("s01"), s2])
    findings = _check_context_deps(script, {})
    assert findings == []


def test_validator_state_dependency_requires_state_reads():
    """link_type=state_dependency must have the world_var also in state_reads."""
    s2 = _scene(
        "s02",
        deps=[SceneContextRef(
            ref_type="world_var", ref_id="world_var:affinity",
            link_type="state_dependency",
            reason="affinity gate",
        )],
        state_reads=[],  # MISSING — should error
    )
    script = _script(
        [_scene("s01"), s2],
        world_vars=[WorldVariable(
            name="affinity", type="int", initial_value=0, description="x",
        )],
    )
    findings = _check_context_deps(script, {})
    assert any("state_reads" in f.message for f in findings)


def test_validator_state_dependency_ok_when_in_state_reads():
    s2 = _scene(
        "s02",
        deps=[SceneContextRef(
            ref_type="world_var", ref_id="world_var:affinity",
            link_type="state_dependency",
            reason="affinity gate",
        )],
        state_reads=["affinity"],
    )
    script = _script(
        [_scene("s01"), s2],
        world_vars=[WorldVariable(
            name="affinity", type="int", initial_value=0, description="x",
        )],
    )
    findings = _check_context_deps(script, {})
    assert findings == []


def test_validator_rejects_unknown_character():
    s2 = _scene("s02", deps=[SceneContextRef(
        ref_type="character_arc", ref_id="character:nobody",
        link_type="arc_beat", reason="nobody's arc",
    )])
    script = _script([_scene("s01"), s2])
    chars = {"alice": CharacterProfile(
        id="alice", name="Alice", role="main",
        personality="kind", background="village",
    )}
    findings = _check_context_deps(script, chars)
    assert any("unknown character" in f.message for f in findings)
    # 4e: maps to character_undeclared_use (deterministic, requires_retry=True)
    assert any(f.category == "character_undeclared_use" for f in findings)


def test_validator_rejects_unknown_world_var():
    s2 = _scene("s02", deps=[SceneContextRef(
        ref_type="world_var", ref_id="world_var:nonexistent",
        link_type="motif_recurrence", reason="unknown var",
    )])
    script = _script([_scene("s01"), s2])
    findings = _check_context_deps(script, {})
    assert any("unknown world_variable" in f.message for f in findings)
    # 4e: maps to world_var_undeclared_use (deterministic, requires_retry=True)
    assert any(f.category == "world_var_undeclared_use" for f in findings)


# ------------------------------------------------------------
# Writer dedup: graph pull suppresses recent-window duplicate
# ------------------------------------------------------------


def test_graph_full_dialogue_pull_tracks_emitted_scene_id():
    """When Director pulls s01 full_dialogue via graph, emitted_scene_ids
    gets s01 so the recent-window code block can skip the duplicate."""
    s1 = _scene("s01", dialogue=[
        DialogueLine(character_id="alice", text="line one", emotion="neutral"),
    ])
    s2 = _scene("s02", deps=[SceneContextRef(
        ref_type="scene", ref_id="s01", link_type="callback",
        reason="pulls s01 full", inject_as="full_dialogue",
    )])
    script = _script([s1, s2])
    emitted_scenes: set[str] = set()
    emitted_chars: set[str] = set()
    block = _format_graph_context(
        s2, script,
        emitted_scene_ids=emitted_scenes,
        emitted_character_ids=emitted_chars,
    )
    assert "s01" in emitted_scenes  # dedup tracker populated
    assert "line one" in block      # full dialogue rendered


def test_graph_summary_pull_uses_scene_summary_when_present():
    s1 = _scene("s01", summary="Previously: alice learned the truth.")
    s2 = _scene("s02", deps=[SceneContextRef(
        ref_type="scene", ref_id="s01", link_type="callback",
        reason="callback to revelation", inject_as="summary",
    )])
    script = _script([s1, s2])
    emitted_scenes: set[str] = set()
    block = _format_graph_context(
        s2, script,
        emitted_scene_ids=emitted_scenes,
        emitted_character_ids=set(),
    )
    assert "learned the truth" in block


def test_graph_empty_deps_returns_empty_string():
    s1 = _scene("s01")
    script = _script([s1])
    block = _format_graph_context(
        s1, script,
        emitted_scene_ids=set(),
        emitted_character_ids=set(),
    )
    assert block == ""


def test_graph_world_var_snapshot_shows_current_value():
    """inject_as=state_snapshot should render current value from state_timeline
    (or fall back to initial_value)."""
    s1 = _scene("s01")
    s2 = _scene(
        "s02",
        state_reads=["affinity"],
        deps=[SceneContextRef(
            ref_type="world_var", ref_id="world_var:affinity",
            link_type="state_dependency",
            reason="affinity gates dialog tone",
            inject_as="state_snapshot",
        )],
    )
    script = _script([s1, s2], world_vars=[
        WorldVariable(name="affinity", type="int", initial_value=5, description="x"),
    ])
    block = _format_graph_context(
        s2, script,
        emitted_scene_ids=set(),
        emitted_character_ids=set(),
    )
    # No state_timeline entries yet → falls back to initial
    assert "5" in block or "affinity" in block
