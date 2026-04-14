"""State Orchestrator Agent (Sprint 9-6).

Runs AFTER StructureReviewer, BEFORE Writer. Translates the symbolic
world_state dict into concise English narrative-constraint text that
Writer can follow without having to interpret raw variables.

Example input:
  world_state = {
    "manuscript_read": True,
    "affinity_kael_mira": 6,
  }
  scenes = [Scene(id="ch3", state_reads=["manuscript_read"], ...)]
  world_variables = [WorldVariable("affinity_kael_mira", type="int",
                                    initial=3, description="0-10 emotional closeness")]

Example output:
  state_constraints = '''
  Scene ch3:
    - Mira has already read the manuscript. Do not have her react as if
      discovering it for the first time.
  '''

Writer then receives this as an explicit block in the prompt above
strategy_guidance. Keeps Writer's creative work (dialogue craft)
decoupled from the logical work (state interpretation). Cost: 1 Haiku
call per pipeline run, ~$0.002.

Empty world_state → skip entirely (pass-through node).
"""
from __future__ import annotations

import json
import logging

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.services.llm import ainvoke_llm

logger = logging.getLogger(__name__)


STATE_ORCHESTRATOR_SYSTEM = """You compile symbolic world state into \
narrative constraints that a dialogue Writer can honor.

Given:
  - a list of declared world_variables (name, type, initial, description)
  - the CURRENT value of each variable (reflecting scene writes so far)
  - scene-level state_reads (which variables each scene consults)

Produce a short, scene-by-scene constraint block in plain English. \
For each scene that has state_reads, state exactly what the current \
state IMPLIES for the dialogue — what the characters already know, what \
they cannot discover for the first time, what relationships / items / \
flags are in effect.

Rules:
- Constraints are directives to Writer, not descriptions for the reader
- 1-3 constraints per scene, each one line
- If a scene has empty state_reads, OMIT it entirely
- Use character-level language ("Mira already knows X"), not \
variable-level ("manuscript_read is True")
- Reference affinity/trust values qualitatively ("formal address", \
"past first-name stage") not numerically

Output format: plain text, one scene block at a time:

Scene ch1:
  - <constraint 1>
  - <constraint 2>

Scene ch3:
  - <constraint>

Do NOT add commentary before or after. Do NOT use JSON. Do NOT use \
<thinking> tags."""


async def run_state_orchestrator(state: AgentState) -> dict:
    """Compile world_state → narrative constraint text for Writer.

    Sprint 9-6 + Gemini-review fix: simulates the state TIMELINE, not
    the snapshot. The initial version fed ALL scenes the initial
    world_state, which meant late-game scenes received constraints as
    if no state_writes had happened yet — classic time-travel bug.

    Fix: walk scenes in order, apply each scene's state_writes AFTER
    compiling constraints for it, and send the LLM a per-scene view
    of the effective state at scene-start time.
    """
    script = state.get("vn_script")
    if not script or not script.world_variables:
        # No declared world variables → nothing to orchestrate.
        return {"state_constraints": ""}

    # Collect scenes that actually read state — no point spending
    # Haiku tokens on scenes that won't use the output.
    reading_scenes = [s for s in script.scenes if s.state_reads]
    if not reading_scenes:
        return {"state_constraints": ""}

    # Build a per-scene effective state by walking the full scene list in
    # order and applying state_writes sequentially. Each reading scene
    # gets the state AT ITS START (before its own writes apply).
    effective_state: dict = {
        v.name: v.initial_value for v in script.world_variables
    }
    per_scene_state: dict[str, dict] = {}
    for s in script.scenes:
        if s.state_reads:
            # Capture a snapshot for this scene's start
            per_scene_state[s.id] = dict(effective_state)
        if s.state_writes:
            for var, val in s.state_writes.items():
                effective_state[var] = val

    variables_block = "\n".join(
        f"  {v.name} ({v.type}): {v.description}" for v in script.world_variables
    )
    # Per-scene effective state block (this is the core fix)
    scenes_block_lines = []
    for s in reading_scenes:
        snapshot = per_scene_state.get(s.id, {})
        # Show just the values the scene reads, not the whole state
        relevant = {k: snapshot.get(k) for k in s.state_reads if k in snapshot}
        scenes_block_lines.append(
            f"  {s.id} ({s.title}): reads {s.state_reads}\n"
            f"    effective state at scene start: "
            f"{json.dumps(relevant, ensure_ascii=False)}"
        )
    scenes_block = "\n".join(scenes_block_lines)

    user_prompt = (
        f"Declared world_variables:\n{variables_block}\n\n"
        f"Per-scene state (timeline-simulated):\n{scenes_block}\n\n"
        "Compile per-scene narrative constraints. Each scene's constraints "
        "MUST reflect the state values shown above for THAT scene, not "
        "some global snapshot."
    )

    settings = get_settings()
    try:
        response = await ainvoke_llm(
            STATE_ORCHESTRATOR_SYSTEM,
            user_prompt,
            model=settings.llm_state_orchestrator_model,
            caller="state_orchestrator",
        )
        content = (
            response.content if hasattr(response, "content") else str(response)
        ).strip()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"StateOrchestrator failed: {e} — passing through")
        return {"state_constraints": ""}

    logger.info(
        f"StateOrchestrator compiled constraints for {len(reading_scenes)} "
        f"state-reading scenes ({len(content)} chars)"
    )
    return {"state_constraints": content}
