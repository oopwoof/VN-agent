"""Vision LLM judge for one composited playtest frame.

Follows the `llm=None` injection convention used throughout this codebase
(`chat_ops/intent_router.py::classify_intent`, `assets/web_search_agent.py::
plan_queries`): callers can inject a fake `llm` callable for tests; real
calls lazily import `ainvoke_llm` and resolve the configured judge model.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from vn_agent.playtest.schema import PlaytestFrameJudgment, WalkNode

logger = logging.getLogger(__name__)

PLAYTEST_JUDGE_SYSTEM = """You are a visual novel playtest judge. You are shown ONE rendered \
frame from a visual novel (a composited scene image with a dialogue box, or a choice menu), \
along with the scene's dialogue context. Judge this single frame on four dimensions:

- ui_coherence_score (1-5): does the frame look like a coherent, readable VN screen? Penalize \
missing/blank art (flat gray "[missing background]" panels, unlabeled colored boxes standing \
in for character sprites), overlapping or cut-off text, and illegible layout. A frame with \
real, well-composed art and a clean dialogue box scores 5; a frame that is entirely missing \
art (only placeholder labels) scores no higher than 2.
- dead_end_risk ("none"/"low"/"high"): does this frame look like a narrative dead end — a \
scene with no dialogue, a choice menu with zero enabled (unlocked) options, or dialogue that \
reads as an abrupt, unmotivated stop?
- interactivity_pacing_score (1-5): for a choice_menu frame, are there a reasonable number of \
distinct, meaningful-sounding options (not 1, not a wall of 6+)? For a scene frame, does the \
visible dialogue read as appropriately paced (not a single fragment, not a wall of text)?
- player_agency_score (1-5): for a choice_menu frame, do the choice texts sound like they lead \
to meaningfully different outcomes (not cosmetically identical rephrasings)? For a scene frame \
with no choices, score 3 (neutral — this dimension isn't directly assessable from a non-choice \
frame).

List up to 5 findings (category one of ui_coherence/dead_end/pacing/player_agency/advisory, \
short message, severity info/warning/critical) ONLY for things actually visible or inferable \
from what's given — do not invent plot problems. Write a one-sentence summary."""

_DEFAULT_MODEL = "claude-sonnet-4-6"


def _build_user_prompt(node: WalkNode) -> str:
    lines = [f"Scene: {node.scene_title} ({node.scene_id})", f"Frame kind: {node.kind}"]
    if node.dialogue_excerpt:
        lines.append("Dialogue context:")
        lines.extend(f"  {d}" for d in node.dialogue_excerpt)
    if node.kind == "choice_menu":
        lines.append(f"Enabled choices: {node.choice_texts or '(none)'}")
        if node.locked_choice_texts:
            lines.append(f"Locked/gated choices (not currently available): {node.locked_choice_texts}")
    return "\n".join(lines)


def _downscale_for_llm(frame_path: Path, max_dim: int = 896) -> bytes:
    """Downscale to at most `max_dim` on the longer side, return PNG bytes.
    PNG (not JPEG) — frames are flat synthetic UI with text the judge needs
    to read; JPEG's chroma subsampling would blur it, and PNG stays small
    anyway on this kind of flat-color content."""
    img = Image.open(frame_path).convert("RGB")
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def judge_frame(
    frame_path: Path,
    node: WalkNode,
    *,
    llm=None,
    model: str | None = None,
) -> PlaytestFrameJudgment:
    """Judge one composited frame. Raises on LLM/parse failure — callers
    (agent.py) catch per-frame so one bad frame degrades to `judge_error`
    instead of losing the whole report."""
    if llm is None:
        from vn_agent.services.llm import ainvoke_llm as _ainvoke
        try:
            from vn_agent.config import get_settings
            model = model or getattr(get_settings(), "llm_playtest_judge_model", None) or _DEFAULT_MODEL
        except Exception:  # noqa: BLE001
            model = model or _DEFAULT_MODEL
        llm = _ainvoke
    else:
        model = model or _DEFAULT_MODEL

    image_bytes = _downscale_for_llm(frame_path)
    result = await llm(
        PLAYTEST_JUDGE_SYSTEM,
        _build_user_prompt(node),
        schema=PlaytestFrameJudgment,
        model=model,
        caller=f"playtest/judge/{node.node_id}",
        images=[image_bytes],
    )
    if not isinstance(result, PlaytestFrameJudgment):
        raise RuntimeError(f"judge_frame got non-schema result: {type(result)!r}")
    return result
