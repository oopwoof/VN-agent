"""Core VN script schema models."""
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .music import MusicCue


class DialogueLine(BaseModel):
    character_id: str | None = Field(default=None, description="Speaker ID, None for narration")
    text: str = Field(description="Dialogue or narration text")
    emotion: str = Field(default="neutral", description="Speaker emotion for this line")


class WorldVariable(BaseModel):
    """Symbolic state variable declared by Director, read/written by scenes.

    Sprint 9-1: turns cross-scene continuity from "hope Sonnet remembers"
    into "hard symbolic state that survives long context." Flags, items,
    affinity, key-and-lock mechanics all live here. Ren'Py compiler
    (Sprint 9-4) emits `default var_name = initial_value` at init time
    and `$ var_name = value` inside scene labels where writes happen.
    """
    name: str = Field(description="Python-identifier-valid variable name")
    type: Literal["bool", "int", "string", "enum"] = Field(
        description="Type hint for the Ren'Py compiler and consistency check"
    )
    initial_value: Any = Field(
        description="Value at story start. Type must match `type` field."
    )
    description: str = Field(
        description="What this variable tracks, human-readable. Used by "
                    "StateOrchestrator (Sprint 9-6) to compile narrative constraints."
    )
    enum_values: list[str] | None = Field(
        default=None,
        description="For type='enum', the allowed values. Ignored otherwise.",
    )


class SceneContextRef(BaseModel):
    """Phase 13-1 / Step 5: Director-declared narrative dependency on a
    prior entity. Used to give Writer deterministic context pulls instead
    of relying on cosine top-k lottery (which can evict premise / callback
    scenes under long-run drift).

    Emitted by Director at planning time (step-2). Validated by
    StructureReviewer for consistency (no forward refs, no self-loops,
    state_dependency refs must appear in state_reads, ref_id must exist).
    Consumed by Writer via _format_graph_context + canonical dedup.

    ref_id format by ref_type:
      scene         → "s03" (bare scene.id)
      character_arc → "character:{id}"
      world_var     → "world_var:{name}"
      motif         → "motif:{tag}"
      location      → "location:{bg_id}"
    """
    ref_type: Literal["scene", "character_arc", "world_var", "motif", "location"]
    ref_id: str = Field(
        description="Backward reference. Format depends on ref_type — see class doc.",
    )
    link_type: Literal[
        "callback", "foreshadow_payoff", "arc_beat",
        "state_dependency", "motif_recurrence",
    ]
    reason: str = Field(
        ..., max_length=200,
        description="One sentence explaining why this dep exists. "
                    "Lets Writer prefix each injected block with a header.",
    )
    inject_as: Literal[
        "full_dialogue", "summary", "state_snapshot", "character_arc_so_far",
    ] = "summary"


class SceneBrief(BaseModel):
    """Phase 13-2 Step 1 (路线四): per-scene creative instructions, produced
    by Director step2 alongside navigation/music/state I/O. The downstream
    Writer-parallel workers (route 4 Step 2+) consume these as the plan
    skeleton before going to thinking fanout.

    Designed to be dense: `beats` is the creative spine, `character_blocking`
    answers "where are they physically/relationally", `emotional_curve`
    tracks the interior arc, `tension_target` sets expected energy,
    `subtext_notes` is what's UNSAID between lines.

    All fields are hard-capped at small sizes (beats ≤ 7, curve ≤ 5) so a
    misbehaving Director can't blow up the Writer prompt when this gets
    consumed later.
    """
    beats: list[str] = Field(
        default_factory=list,
        description="3-7 ordered scene beats (each ≤80 chars). The creative spine "
                    "Writer workers will inflate into dialogue.",
    )
    character_blocking: dict[str, str] = Field(
        default_factory=dict,
        description="{character_id: position/movement/posture} for each "
                    "characters_present. e.g. {'yui': 'leans on the railing, "
                    "back to the lamp'}.",
    )
    emotional_curve: list[str] = Field(
        default_factory=list,
        description="2-5 emotion labels in order, tracking the scene's "
                    "internal arc (e.g. ['apprehension','recognition','grief']).",
    )
    tension_target: Literal["low", "medium", "high", "climax"] = Field(
        default="medium",
        description="Expected energy level for this scene.",
    )
    subtext_notes: str = Field(
        default="", max_length=400,
        description="What stays UNSAID between lines. Drives voice/restraint "
                    "choices downstream.",
    )

    @field_validator("beats")
    @classmethod
    def _cap_beats(cls, v: list[str]) -> list[str]:
        # Hard ceiling — keeps Writer prompt bounded even if Director
        # over-produces. Deterministic truncation (keep first 7) is safer
        # than raising a validation error and risking a pipeline abort.
        return list(v)[:7]

    @field_validator("emotional_curve")
    @classmethod
    def _cap_emotional_curve(cls, v: list[str]) -> list[str]:
        return list(v)[:5]


class SceneThinking(BaseModel):
    """Phase 13-2 Step 2 (路线四): per-scene creative planning artifact.

    Produced by the `thinking_fanout` node (Haiku-level, sequential for
    now — Step 4 moves to parallel). The job of a thinking worker is to
    read scene_brief + context_deps + prior-scene summaries + macro_reference
    and emit a STRUCTURED plan that later Writer workers can coordinate on.

    This is intentionally NOT dialogue. The whole point of decoupling
    thinking from writing is to let workers "see what each other plan to
    write" before any dialogue commits — eliminates the two-worker-
    plants-the-same-callback problem that naive parallel writing hits.

    Step 3 (`cross_ref_sync`) will give workers one chance to amend their
    thinking after seeing peers'; Step 4 (`writing_fanout`) freezes thinking
    and fans Sonnet writers out in parallel.
    """
    writing_intent: str = Field(
        default="", max_length=300,
        description="One sentence on what this scene is TRYING to achieve "
                    "narratively/emotionally. Drives voice + pacing choices.",
    )
    key_beats_expanded: list[str] = Field(
        default_factory=list,
        description="Expanded beat descriptions (≤120 chars each). Adds "
                    "subtext / causality beyond scene_brief.beats shorthand.",
    )
    callback_plan: list[dict] = Field(
        default_factory=list,
        description="Explicit callback slots {ref_scene_id: str, "
                    "what_lands: str}. Must match scene.context_deps "
                    "(StructureReviewer-validated at plan time); thinking "
                    "phase just plans HOW each callback will land.",
    )
    opening_hook: str = Field(
        default="", max_length=200,
        description="How the scene opens — one line of stage direction or "
                    "action that sets tone.",
    )
    closing_beat: str = Field(
        default="", max_length=200,
        description="How the scene ends — the last emotional chord, "
                    "transition into next scene's entry_context.",
    )
    voice_notes: dict[str, str] = Field(
        default_factory=dict,
        description="Per-character voice reminders SPECIFIC to this scene "
                    "(e.g. {'yui': 'tighter cadence here — she's guarding'}). "
                    "Layered on top of macro_reference.character_voice_charter.",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Known failure modes Writer should avoid (e.g. 'don't "
                    "over-explain the watch — subtext only'). Harvested from "
                    "scene_brief.subtext_notes + macro_reference.tone_register.",
    )

    @field_validator("key_beats_expanded")
    @classmethod
    def _cap_beats(cls, v: list[str]) -> list[str]:
        return list(v)[:8]

    @field_validator("risks")
    @classmethod
    def _cap_risks(cls, v: list[str]) -> list[str]:
        return list(v)[:6]


class BranchOption(BaseModel):
    text: str = Field(description="Choice text shown to player")
    next_scene_id: str = Field(description="Scene to jump to when this option is chosen")
    condition: str | None = Field(default=None, description="Optional condition expression")
    # Sprint 9-1: symbolic guard on branch visibility. Rendered as Ren'Py
    # `if requires_key == value:` wrapping the menu option. Empty dict
    # (default) means "always visible."
    requires: dict[str, Any] = Field(
        default_factory=dict,
        description="Symbolic guard: {var_name: expected_value} — branch only "
                    "shown when all conditions match world_state.",
    )


class Scene(BaseModel):
    id: str = Field(description="Unique scene identifier, used as Ren'Py label")
    title: str = Field(description="Human-readable scene title")
    description: str = Field(description="Scene description for asset generation")
    background_id: str = Field(description="Background image identifier")
    music: MusicCue | None = Field(default=None, description="BGM for this scene")
    characters_present: list[str] = Field(default_factory=list, description="Character IDs present in scene")
    dialogue: list[DialogueLine] = Field(default_factory=list)
    branches: list[BranchOption] = Field(default_factory=list, description="Player choices at end of scene")
    next_scene_id: str | None = Field(default=None, description="Auto-advance to scene, None if branches exist")
    narrative_strategy: str | None = Field(default=None, description="Narrative strategy used in this scene")
    background_prompt: str | None = Field(default=None, description="Image generation prompt for background")
    # Transition cards for cross-scene coherence (Sprint 6-1)
    entry_context: str | None = Field(
        default=None,
        description="What the player just experienced before this scene — given to Writer for continuity",
    )
    exit_hook: str | None = Field(
        default=None,
        description="How this scene should end to set up the next one — given to Writer",
    )
    emotional_arc: str | None = Field(
        default=None,
        description="Emotional arc of this scene, e.g. 'warmth → anticipation'",
    )
    # Sprint 9-1: symbolic state I/O. state_reads declares which variables
    # this scene's dialogue depends on — Writer prompt injects their
    # current values. state_writes declares {var: new_value} that takes
    # effect when this scene ends (emitted as `$ var = value` in Ren'Py).
    state_reads: list[str] = Field(
        default_factory=list,
        description="Names of world_variables this scene's dialogue depends on. "
                    "StateOrchestrator pulls current values from world_state.",
    )
    state_writes: dict[str, Any] = Field(
        default_factory=dict,
        description="World-state updates this scene makes when it completes. "
                    "Ren'Py compiler emits `$ var_name = value` lines.",
    )
    # Sprint 11-1: ≤100-word Haiku-generated summary of this scene's events,
    # emotional pivot, and state changes. Populated after the scene is
    # written + reviewed. Used by downstream scenes (15+) to carry long-form
    # context without sending full dialogue (drift-bounded recursive
    # summarization). None when summarization is disabled.
    summary: str | None = Field(
        default=None,
        description="Post-hoc Haiku summary (~100 words). None until populated "
                    "by the summarizer. Used for long-form memory in scripts "
                    "beyond the writer_context_window.",
    )
    # Phase 13-1 / Step 4: cache key for summary re-use. Writer computes
    # dialogue_digest(scene) before calling summarize_scene; if the stored
    # hash matches, the existing summary is kept and the Haiku call is
    # skipped. Revision loops on a 50-scene run would otherwise re-fire
    # summarize_scene × revision_count × scene_count times (150 wasted
    # Haiku calls on a single 50-scene × 3-revision run).
    summary_dialogue_hash: str | None = Field(
        default=None,
        description="SHA1[:16] over (character_id, emotion, text) triples of "
                    "this scene's dialogue. Cache key for summarize_scene "
                    "re-use across revision loops.",
    )
    # Phase 13-1 / Step 5: Director-declared narrative deps. Up to 5 strong
    # dependencies (≥0.7 confidence) — prior scenes this scene calls back
    # to, character arcs it advances, world_vars it reads, motifs it invokes.
    # StructureReviewer validates: no forward refs, no self-loops, ref must
    # exist, state_dependency refs must also appear in state_reads.
    context_deps: list[SceneContextRef] = Field(
        default_factory=list, max_length=5,
        description="Director-declared narrative dependencies. Writer pulls "
                    "these into prompt BEFORE cosine retrieval; chapter rollup "
                    "preserves graph-pinned scenes verbatim.",
    )

    @field_validator("context_deps")
    @classmethod
    def _cap_context_deps(cls, v: list) -> list:
        """Safety cap in case Pydantic's max_length isn't enforced by a
        specific version — 5 is a firm ceiling (budget design)."""
        return list(v)[:5]

    # Phase 13-2 Step 1: Director step2 creative brief. Consumed by the
    # route-4 Writer-parallel pipeline once Steps 2-6 land. Optional so
    # older vn_script.json files (and small-model Director runs that
    # skip brief generation) still load fine.
    scene_brief: SceneBrief | None = Field(
        default=None,
        description="Director-declared per-scene creative instructions "
                    "(Phase 13-2 Step 1). Consumed by Writer workers in "
                    "route-4 fanout-sync-fanout parallelization.",
    )
    # AUDITS §2 piggyback (2026-04-24): snapshot of the StateOrchestrator
    # constraint text that Writer was shown when writing this scene. Lets
    # debug/front-end retrospectively see the "directive" the Writer read
    # — without this, state_constraints was ephemeral in AgentState and
    # lost on every reload.
    state_constraints_seen: str | None = Field(
        default=None,
        description="Frozen copy of state_constraints (StateOrchestrator "
                    "output) as Writer saw it when writing this scene. "
                    "None when no state constraints were active.",
    )
    # Phase 13-2 Step 2 (route 4): per-scene thinking plan produced by
    # thinking_fanout before Writer runs. Later (Step 4) Writer workers
    # consume this to coordinate voice/callbacks across parallel writes.
    # Optional — runs only when enable_thinking_fanout + scene count ≥ min.
    thinking: SceneThinking | None = Field(
        default=None,
        description="Pre-write creative plan (thinking_fanout output). "
                    "Consumed by parallel Writer workers in route-4 Step 4.",
    )


class Chapter(BaseModel):
    """Phase 13-1 / Step 6: chapter-level rollup for long-form VN memory.

    Produced by summarizer.rollup_chapter after every N scenes
    (chapter_rollup_every, default 10). The rollup is a FLAT-INDEX
    summary computed directly from the raw scenes — NOT from prior
    chapter summaries — to avoid "telephone-game" drift across 5+
    chapter rollups (Gemini 3 Pro BLOCKER #2).

    pinned_scene_ids carries the subset of this chapter's scenes that are
    targets of graph context_deps from LATER scenes; the rollup prompt
    instructs Haiku to preserve those scenes' dialogue excerpts verbatim
    rather than compressing them (they have load-bearing narrative weight).
    """
    chapter_id: str = Field(description='Stable id, e.g. "ch01", "ch02"')
    scene_ids: list[str] = Field(description="Member scene ids in order")
    summary: str | None = Field(
        default=None,
        description="Haiku dynamic-length (200-800 word) rollup of the "
                    "member scenes. Populated async after the chapter closes.",
    )
    # Cache keys: members' summary_dialogue_hash. If any member's hash
    # changes (local_regen, revision splice), rollup is re-fired.
    summary_scene_hashes: list[str] = Field(default_factory=list)
    world_state_after: dict[str, Any] = Field(
        default_factory=dict,
        description="world_state snapshot at this chapter's end.",
    )
    pinned_scene_ids: list[str] = Field(
        default_factory=list,
        description="Member scenes referenced by later scenes via graph "
                    "context_deps. Rollup preserves these verbatim.",
    )


class MacroReference(BaseModel):
    """Phase 13-2 Step 1 (路线四): global writing reference shared across
    every Writer worker.

    Director step1 emits this as part of the outline. Once route-4 Step 3
    lands, it flows into the monolithic 1-hour cache prefix (Phase 13-1
    Step 3), so every parallel Writer call reads the same character voice
    charter and tone register at amortized-zero cost. Addresses the
    primary risk of fanout parallelism: character voice drift and pacing
    imbalance across 50+ scenes written by independent workers.

    All fields are Optional-shaped (empty string / empty list / empty
    dict). Short demos (≤6 scenes) can leave most blank — Director prompt
    explicitly says so to avoid wasted tokens on short runs.
    """
    theme_thesis: str = Field(
        default="", max_length=300,
        description="One sentence capturing the story's central tension "
                    "(e.g. 'duty vs memory in the three hours before the tide').",
    )
    pacing_arc: str = Field(
        default="", max_length=500,
        description="Dense phrase mapping scene ranges to strategies "
                    "(e.g. 'accumulate s01-04 → rupture s05 → uncover s06-07 "
                    "→ resolve s08').",
    )
    foreshadow_plan: list[dict] = Field(
        default_factory=list,
        description="Major foreshadow→payoff links. Each entry is a dict "
                    "like {planted_in: scene_id, payoff_in: scene_id, element: str}. "
                    "2-5 entries for most stories; [] for simple/short runs.",
    )
    character_voice_charter: dict[str, str] = Field(
        default_factory=dict,
        description="{character_id: one-line voice anchor}. ≤150 chars each. "
                    "Read by every Writer worker to keep voice consistent.",
    )
    tone_register: str = Field(
        default="", max_length=200,
        description="Unified language register — literary / action / mixed, "
                    "plus POV and default tension.",
    )


class StateTimelineEntry(BaseModel):
    """One row in VNScript.state_timeline (Phase 13-1 Step 2).

    state_after is the FULL world_state dict after this scene's state_writes
    have been applied — not a delta. Caching the full snapshot makes
    front-end rendering and debug inspection O(1) instead of O(N) fold.
    """
    scene_id: str = Field(description="Scene this snapshot captures the post-state of")
    state_after: dict[str, Any] = Field(
        default_factory=dict,
        description="Full world_state after the scene's state_writes merged in. "
                    "Not a delta — complete snapshot.",
    )


class VNScript(BaseModel):
    title: str = Field(description="Visual novel title")
    description: str = Field(description="Story premise and overview")
    theme: str = Field(description="Original theme/prompt from user")
    start_scene_id: str = Field(description="ID of the first scene")
    scenes: list[Scene] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list, description="Character IDs referenced in this script")
    revision_count: int = Field(default=0, description="Number of revision rounds completed")
    revision_notes: list[str] = Field(default_factory=list, description="Feedback from each revision round")
    # Sprint 9-1: Director declares world variables up front. Empty list
    # (default) = story has no symbolic state; all continuity is textual.
    # Having any entry here switches on Ren'Py compiler's state emission
    # (Sprint 9-4) and the StateOrchestrator pre-Writer node (Sprint 9-6).
    world_variables: list[WorldVariable] = Field(
        default_factory=list,
        description="Typed symbolic state declared by Director. "
                    "Read/written by scenes, enforced by DialogueReviewer, "
                    "emitted into Ren'Py $ var = value.",
    )
    # Phase 13-1 / Step 2: top-level state time series for long-form runs.
    # Each entry captures world_state immediately AFTER scene N's state_writes
    # have been applied. Appended by writer.run_writer after each scene
    # completes, hard-truncated by local_regen on splice (see local_regen
    # docstring). Linear (non-branch-aware) — branch DAG walker deferred.
    #
    # Redundant with fold(scenes[:N].state_writes) but explicit caching means
    # (a) Web API / front-end renders without reconstructing, (b) debug tools
    # can inspect state at scene N without replaying, (c) hard-truncate on
    # splice prevents poisoned downstream entries from polluting Writer context.
    state_timeline: list[StateTimelineEntry] = Field(
        default_factory=list,
        description="Per-scene world_state snapshots, post-state_writes. "
                    "Appended by Writer, hard-truncated by local_regen on splice.",
    )
    # Phase 13-1 / Step 6: chapter rollups. Populated by Writer after every
    # `chapter_rollup_every` scenes (default 10, fires only when total
    # scenes ≥ chapter_rollup_min_scenes so short demos stay unchanged).
    # Rollup is async fire-and-forget; next chapter's Writer call awaits
    # pending rollups before assembling its monolithic cache prefix.
    chapters: list[Chapter] = Field(
        default_factory=list,
        description="Haiku chapter rollups (≤800 words each). Stable within "
                    "a chapter, updated at chapter boundaries. Fed into the "
                    "cached system prefix by the Writer prompt assembler.",
    )
    # Phase 13-2 Step 1 (route 4): global writing reference produced by
    # Director step1. Optional so older vn_script.json files still load.
    # Once route-4 Step 3 lands, this feeds the monolithic cache prefix
    # (Phase 13-1 Step 3) so every Writer worker shares the same voice
    # charter / pacing arc / foreshadow plan at amortized-zero cost.
    macro_reference: MacroReference | None = Field(
        default=None,
        description="Director-declared global writing reference (Phase 13-2 "
                    "Step 1). Feeds route-4 Writer-parallel pipeline via the "
                    "monolithic 1h cache prefix.",
    )
