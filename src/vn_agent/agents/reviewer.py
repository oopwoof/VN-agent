"""Reviewer Agent: Validates script integrity and coherence."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import REVIEWER_SYSTEM, strip_thinking
from vn_agent.schema.script import Scene, VNScript
from vn_agent.services.llm import ainvoke_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = REVIEWER_SYSTEM


@dataclass
class ReviewResult:
    passed: bool
    feedback: str
    issues: list[str]
    scores: dict[str, float] | None = None  # {coherence, voice, arc, branches, pacing, avg}


async def run_reviewer(state: AgentState) -> dict:
    """Reviewer node: validates the current script."""
    script = state["vn_script"]
    if not script:
        return {
            "review_passed": False,
            "review_feedback": "No script to review",
            "revision_count": state.get("revision_count", 0) + 1,
        }

    # Sprint 7-5b review flow:
    #   1. Structural check (scene graph reachability, branch targets valid)
    #   2. Mechanical check (line counts, character IDs, emotion tags)
    #   3. LLM quality check (Sonnet, craft rubric only — voice/subtext/arc)
    # The first two are pure Python, deterministic, cheap. If either fails
    # we return precise feedback without spending a Sonnet call — the
    # feedback is already actionable ("scene X has 2 lines, needs 5-20").
    structural_result = _structural_check(script)
    if not structural_result.passed:
        logger.info(f"Reviewer: {len(structural_result.issues)} structural issues")
        return {
            "review_passed": False,
            "review_feedback": structural_result.feedback,
            "revision_count": state.get("revision_count", 0) + 1,
        }

    characters = state.get("characters", {}) or {}
    settings = get_settings()
    mechanical_result = _mechanical_check(script, characters, settings)
    if not mechanical_result.passed:
        logger.info(
            f"Reviewer: {len(mechanical_result.issues)} mechanical issues "
            f"(skipping LLM quality check — Writer must fix format first)"
        )
        return {
            "review_passed": False,
            "review_feedback": mechanical_result.feedback,
            "revision_count": state.get("revision_count", 0) + 1,
        }

    # Then LLM quality check (can be skipped for budget-sensitive runs)
    if settings.reviewer_skip_llm:
        logger.info("Reviewer: skipping LLM quality check (reviewer_skip_llm=True)")
        result = structural_result
    else:
        quality_result = await _quality_check(script)
        result = quality_result
    # Strategy consistency check (warnings only, non-blocking)
    strategy_warnings = check_strategy_consistency(script)
    if strategy_warnings:
        for w in strategy_warnings:
            logger.warning(f"Strategy consistency: {w}")

    # Branch divergence check — semantic validation that branches actually
    # produce different experiences (Sprint 6-7). Complements Director's
    # structural check with post-hoc content-level validation.
    divergence_warnings = _check_branch_divergence(script)
    if divergence_warnings:
        for w in divergence_warnings:
            logger.warning(f"Branch divergence: {w}")

    feedback = result.feedback
    if strategy_warnings:
        feedback += "\n\nStrategy consistency warnings:\n" + "\n".join(f"- {w}" for w in strategy_warnings)
    if divergence_warnings:
        feedback += "\n\nBranch divergence warnings:\n" + "\n".join(f"- {w}" for w in divergence_warnings)

    if result.scores:
        logger.info(f"Reviewer scores: {result.scores}")
    logger.info(f"Reviewer result: {'PASS' if result.passed else 'FAIL'} - {result.feedback[:80]}")

    return {
        "review_passed": result.passed,
        "review_feedback": feedback,
        "review_scores": result.scores,
        "revision_count": state.get("revision_count", 0) + 1,
    }


_VALID_EMOTIONS = {
    "neutral", "happy", "sad", "angry", "surprised",
    "scared", "thoughtful", "loving", "determined",
}


def _mechanical_check(
    script: VNScript, characters: dict, settings,
) -> ReviewResult:
    """Pure-Python format audit — fails fast on writer output defects.

    Runs between _structural_check (scene graph) and _quality_check (LLM
    craft judgment). Catches defects that need Writer to fix the output
    format rather than improve the craft:
      - dialogue line count outside [min_dialogue_lines, max_dialogue_lines]
      - character_id values that don't match the cast
      - emotion tags outside the enum Ren'Py knows about
      - empty dialogue (no lines at all)

    Keeps the Sonnet reviewer free to focus on narrative craft — if
    it's brought in at all, the script is at least mechanically valid.
    """
    issues: list[str] = []
    cast = set(characters.keys())

    min_lines = settings.min_dialogue_lines
    max_lines = settings.max_dialogue_lines

    for scene in script.scenes:
        n = len(scene.dialogue)
        if n == 0:
            issues.append(f"Scene '{scene.id}': no dialogue lines written")
            continue
        if n < min_lines:
            issues.append(
                f"Scene '{scene.id}': {n} lines (need at least {min_lines})"
            )
        elif n > max_lines:
            issues.append(
                f"Scene '{scene.id}': {n} lines (max {max_lines})"
            )

        for i, line in enumerate(scene.dialogue, 1):
            cid = line.character_id
            # character_id=None is valid (narration)
            if cid is not None and cast and cid not in cast:
                issues.append(
                    f"Scene '{scene.id}' line {i}: character_id '{cid}' "
                    f"not in cast {sorted(cast)}"
                )
            if line.emotion and line.emotion not in _VALID_EMOTIONS:
                issues.append(
                    f"Scene '{scene.id}' line {i}: emotion '{line.emotion}' "
                    f"not in valid set"
                )

    if not issues:
        return ReviewResult(passed=True, feedback="Mechanical checks passed", issues=[])

    feedback = (
        "Mechanical/format issues found — these must be fixed before craft review:\n"
        + "\n".join(f"- {i}" for i in issues[:20])  # cap feedback size
    )
    if len(issues) > 20:
        feedback += f"\n... and {len(issues) - 20} more"
    return ReviewResult(passed=False, feedback=feedback, issues=issues)


def _structural_check(script: VNScript) -> ReviewResult:
    """Fast structural validation without LLM."""
    issues = []
    scene_ids = {s.id for s in script.scenes}

    # Check start scene exists
    if script.start_scene_id not in scene_ids:
        issues.append(f"Start scene '{script.start_scene_id}' not found in scenes")

    # Check all branch references
    for scene in script.scenes:
        for branch in scene.branches:
            if branch.next_scene_id not in scene_ids:
                issues.append(
                    f"Scene '{scene.id}': branch '{branch.text}' references "
                    f"non-existent scene '{branch.next_scene_id}'"
                )
        if scene.next_scene_id and scene.next_scene_id not in scene_ids:
            issues.append(
                f"Scene '{scene.id}': next_scene_id '{scene.next_scene_id}' does not exist"
            )

    # Check reachability (BFS from start)
    reachable = _find_reachable_scenes(script)
    unreachable = scene_ids - reachable
    if unreachable:
        issues.append(f"Unreachable scenes: {', '.join(sorted(unreachable))}")

    # Note: scenes with no exit (no next_scene_id, no branches) are valid terminal endings

    # Check character consistency
    declared_chars = {c.id if hasattr(c, 'id') else c for c in script.characters}
    for scene in script.scenes:
        for line in scene.dialogue:
            if line.character_id and line.character_id not in declared_chars:
                issues.append(
                    f"Scene '{scene.id}': character '{line.character_id}' speaks but is not declared"
                )

    if issues:
        feedback = "Structural issues found:\n" + "\n".join(f"- {i}" for i in issues)
        return ReviewResult(passed=False, feedback=feedback, issues=issues)

    return ReviewResult(passed=True, feedback="Structural checks passed", issues=[])


def _find_reachable_scenes(script: VNScript) -> set[str]:
    """BFS to find all scenes reachable from start."""
    reachable = set()
    queue = [script.start_scene_id]
    scene_map = {s.id: s for s in script.scenes}

    while queue:
        scene_id = queue.pop(0)
        if scene_id in reachable or scene_id not in scene_map:
            continue
        reachable.add(scene_id)
        scene = scene_map[scene_id]
        if scene.next_scene_id:
            queue.append(scene.next_scene_id)
        for branch in scene.branches:
            queue.append(branch.next_scene_id)

    return reachable


async def _quality_check(script: VNScript) -> ReviewResult:
    """LLM-based quality check for narrative coherence.

    Feeds the Reviewer the *full* dialogue of every scene rather than a
    3-line preview. Character Voice and Emotional Arc rubric dimensions
    are essentially unscorable from a preview — the LLM would be guessing
    — and the extra Haiku input tokens cost well under a cent per run.
    """
    scene_blocks: list[str] = []
    for scene in script.scenes:
        exits = []
        if scene.next_scene_id:
            exits.append(f"→ {scene.next_scene_id}")
        for b in scene.branches:
            exits.append(f"[{b.text}] → {b.next_scene_id}")

        dialogue_lines = [
            f"  {d.character_id or 'NARR'} ({d.emotion}): {d.text}"
            for d in scene.dialogue
        ]
        dialogue_block = "\n".join(dialogue_lines) if dialogue_lines else "  (no dialogue written)"

        strategy = scene.narrative_strategy or "unspecified"
        scene_blocks.append(
            f"## {scene.id} — {scene.title}\n"
            f"Description: {scene.description}\n"
            f"Strategy: {strategy} | Exits: {', '.join(exits) or 'TERMINAL'}\n"
            f"Dialogue:\n{dialogue_block}"
        )

    user_prompt = f"""Review this visual novel script in full:

Title: {script.title}
Theme: {script.theme}
Scenes: {len(script.scenes)}

{chr(10).join(scene_blocks)}

Score each rubric dimension (coherence / voice / arc / branches / pacing)
based on the actual dialogue above — not just scene descriptions. If any
character sounds generic or flat, call it out in the voice score.

If the average ≥ 3.5 respond with PASS on its own line.
If average < 3.5, respond FAIL on the first line followed by actionable issues."""

    settings = get_settings()
    response = await ainvoke_llm(SYSTEM_PROMPT, user_prompt, model=settings.llm_reviewer_model, caller="reviewer")
    content = response.content if hasattr(response, 'content') else str(response)
    content = strip_thinking(content)

    stripped = content.strip()
    first_line = stripped.split("\n", 1)[0].strip().upper()

    # Parse numeric scores (format: coherence=X voice=X arc=X branches=X pacing=X avg=X.X)
    scores = _parse_scores(stripped)

    # Threshold-first decision: if the rubric parsed successfully and we have
    # an average, that number is authoritative. This protects against the
    # LLM writing PASS/FAIL inconsistent with its own scores (coherence=2
    # voice=2 arc=2 but declaring PASS, and vice versa). The LLM-emitted
    # verdict becomes the fallback when scores can't be parsed.
    threshold = settings.reviewer_pass_threshold
    has_issues = "\n-" in stripped or "\n*" in stripped or "\n1." in stripped
    llm_said_pass = first_line.startswith("PASS") and not has_issues

    if scores and "avg" in scores:
        is_pass = scores["avg"] >= threshold
        if is_pass != llm_said_pass:
            logger.info(
                f"Reviewer disagreement: LLM said {'PASS' if llm_said_pass else 'FAIL'} "
                f"but avg={scores['avg']} (threshold={threshold}); "
                f"using score-based verdict."
            )
    else:
        is_pass = llm_said_pass

    if is_pass:
        return ReviewResult(passed=True, feedback="Quality check passed", issues=[], scores=scores)

    return ReviewResult(passed=False, feedback=content, issues=[content], scores=scores)


def _parse_scores(text: str) -> dict[str, float] | None:
    """Extract reviewer rubric scores from response text."""
    import re as _re

    scores: dict[str, float] = {}
    # Match patterns like "coherence=4" or "coherence: 4" or "Narrative Coherence (4/5)"
    for key, patterns in {
        # Sprint 7-5b rubric: voice/subtext/arc/pacing/strategy. Older
        # runs with coherence/branches dimensions still parse gracefully
        # (missing keys just drop out of the average).
        "voice": [r"voice[=:\s]+(\d+(?:\.\d+)?)", r"character voice[^0-9]*(\d+)"],
        "subtext": [r"subtext[=:\s]+(\d+(?:\.\d+)?)"],
        "arc": [r"arc[=:\s]+(\d+(?:\.\d+)?)", r"emotional arc[^0-9]*(\d+)"],
        "pacing": [r"pacing[=:\s]+(\d+(?:\.\d+)?)"],
        "strategy": [r"strategy[=:\s]+(\d+(?:\.\d+)?)", r"strategy execution[^0-9]*(\d+)"],
        # Backwards-compat for legacy runs
        "coherence": [r"coherence[=:\s]+(\d+(?:\.\d+)?)", r"narrative coherence[^0-9]*(\d+)"],
        "branches": [r"branches[=:\s]+(\d+(?:\.\d+)?)", r"branch quality[^0-9]*(\d+)"],
    }.items():
        for pattern in patterns:
            m = _re.search(pattern, text, _re.IGNORECASE)
            if m:
                scores[key] = float(m.group(1))
                break

    if not scores:
        return None

    # Compute average if we have at least 3 dimensions
    if len(scores) >= 3:
        scores["avg"] = round(sum(scores.values()) / len(scores), 2)

    return scores


# ── Strategy consistency check (non-blocking warnings) ─────────────────────

_STRATEGY_KEYWORDS: dict[str, list[str]] = {
    "accumulate": ["build", "layer", "gradual", "growing", "deepen", "mount"],
    "erode": ["doubt", "wear", "crumble", "fade", "lose", "weaken", "dissolve"],
    "rupture": ["sudden", "shock", "break", "snap", "slam", "shatter", "cut"],
    "uncover": ["secret", "hidden", "discover", "truth", "realize", "admit", "reveal"],
    "contest": ["refuse", "argue", "push back", "disagree", "resist", "confront"],
    "drift": ["quiet", "casual", "wander", "meander", "idle", "banter", "chat"],
    "escalate": ["escalate", "intensify", "raise", "stakes", "pressure", "urgent"],
    "resolve": ["resolve", "closure", "peace", "reconcile", "settle", "end"],
}


def check_strategy_consistency(script: VNScript) -> list[str]:
    """Check if scene dialogue loosely matches the assigned narrative strategy.

    Returns a list of warning strings (non-blocking).
    """
    warnings: list[str] = []
    for scene in script.scenes:
        strategy = scene.narrative_strategy
        if not strategy or strategy not in _STRATEGY_KEYWORDS:
            continue

        keywords = _STRATEGY_KEYWORDS[strategy]
        dialogue_text = " ".join(line.text.lower() for line in scene.dialogue)

        hits = sum(1 for kw in keywords if kw in dialogue_text)
        if hits == 0 and len(scene.dialogue) >= 3:
            warnings.append(
                f"Scene '{scene.id}': strategy '{strategy}' assigned but no matching "
                f"keywords found in dialogue ({len(scene.dialogue)} lines)"
            )

    return warnings


# ── Branch divergence check (Sprint 6-7) ───────────────────────────────────

_DIVERGENCE_THRESHOLD = 0.8  # Jaccard similarity above this = cosmetic branches


def _tokenize_for_jaccard(text: str) -> set[str]:
    """Lowercase word tokens for similarity comparison. Drops punctuation."""
    import re

    return {t for t in re.sub(r"[^\w]+", " ", text.lower()).split() if len(t) > 2}


def _collect_path_signature(
    scene_map: dict[str, Scene], start_id: str, max_depth: int = 3,
) -> tuple[set[str], set[str], dict[str, int]]:
    """Walk a branch path and collect signature features for comparison.

    Returns (dialogue_tokens, characters_present, emotion_counts) summed over
    all reachable scenes within max_depth hops from start_id.
    """
    reached: set[str] = set()
    frontier: list[tuple[str, int]] = [(start_id, 0)]
    dialogue_tokens: set[str] = set()
    characters: set[str] = set()
    emotion_counts: dict[str, int] = {}

    while frontier:
        sid, depth = frontier.pop(0)
        if sid in reached or depth > max_depth:
            continue
        reached.add(sid)
        scene = scene_map.get(sid)
        if not scene:
            continue
        characters.update(scene.characters_present)
        for line in scene.dialogue:
            dialogue_tokens |= _tokenize_for_jaccard(line.text)
            emotion_counts[line.emotion] = emotion_counts.get(line.emotion, 0) + 1
        next_ids: list[str] = []
        if scene.next_scene_id:
            next_ids.append(scene.next_scene_id)
        next_ids.extend(b.next_scene_id for b in scene.branches if b.next_scene_id)
        for nid in next_ids:
            if nid not in reached:
                frontier.append((nid, depth + 1))

    return dialogue_tokens, characters, emotion_counts


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _check_branch_divergence(script: VNScript) -> list[str]:
    """Post-hoc semantic check: do branch paths actually produce different content?

    For each scene with 2+ branches, collect each path's dialogue tokens,
    characters, and emotion distribution, then compare pairwise. If Jaccard
    similarity on dialogue > threshold AND character sets match AND emotion
    mix is identical, the branches are cosmetic.

    Returns warning strings. Non-blocking — feedback only.
    """
    warnings: list[str] = []
    scene_map = {s.id: s for s in script.scenes}

    for scene in script.scenes:
        if len(scene.branches) < 2:
            continue

        signatures = []
        for b in scene.branches:
            if b.next_scene_id in scene_map:
                signatures.append(
                    (b, _collect_path_signature(scene_map, b.next_scene_id, max_depth=3))
                )

        for i in range(len(signatures)):
            for j in range(i + 1, len(signatures)):
                (b_i, (tok_i, char_i, emo_i)) = signatures[i]
                (b_j, (tok_j, char_j, emo_j)) = signatures[j]
                if not tok_i or not tok_j:
                    continue
                dialogue_sim = _jaccard(tok_i, tok_j)
                same_chars = char_i == char_j
                same_emotions = emo_i == emo_j
                if dialogue_sim >= _DIVERGENCE_THRESHOLD and same_chars and same_emotions:
                    warnings.append(
                        f"Scene '{scene.id}': branches "
                        f"'{b_i.text[:30]}' and '{b_j.text[:30]}' produce near-identical "
                        f"content (Jaccard={dialogue_sim:.2f}) — cosmetic choice."
                    )

    return warnings
