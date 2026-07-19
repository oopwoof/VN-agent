"""Reflection Agent — batch job that distills feedback into meta-rules.

Reads every record from `feedback.store`, groups by verdict, and asks
Haiku for 5-15 concise rules that generalize the pattern. The result
lands at `data/feedback/dynamic_guidelines.json` and is picked up by
Writer's system prompt on next generation (see `prompts/dynamic.py`).

Design decisions
---------------
- Haiku, not Sonnet. Rule extraction is classification-flavored — a
  cheap model handles it, and running this weekly-ish keeps cost
  ~$0.01/run even at 1k records. Matches `feedback_model_selection`.
- Never mutate `all.jsonl`. Records are immutable inputs; the guidelines
  file is the output side of the flywheel.
- Written atomically (tmp + rename) so a crash mid-write doesn't leave a
  corrupt JSON that would kill Writer's next boot.
- `--min-samples` gate. Running the reflection agent on 3 records
  produces nonsense; require at least N (default 20) or --force.
- Confidence is emitted per rule so future callers can rank/dedup.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from vn_agent.feedback import store as fb_store

logger = logging.getLogger(__name__)


_GUIDELINES_NAME = "dynamic_guidelines.json"
_DEFAULT_MIN_SAMPLES = 20
_DEFAULT_MAX_RULES = 15


def _guidelines_path() -> Path:
    return fb_store._root() / _GUIDELINES_NAME


@dataclass
class Guideline:
    """One rule Writer's system prompt will absorb."""
    text: str
    polarity: str = "avoid"          # "avoid" | "prefer"
    confidence: float = 0.5          # [0, 1]; higher = more sample support
    source_count: int = 0            # how many feedback records back this rule
    example_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReflectionReport:
    """What the batch job wrote. Callers log this + optionally persist alongside."""
    generated_at: str = ""
    total_records: int = 0
    downvote_count: int = 0
    upvote_count: int = 0
    rules: list[Guideline] = field(default_factory=list)
    stopped_reason: str = ""         # "ok" | "insufficient_samples" | "llm_failed" | "no_reasons"
    llm_model: str = ""

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "total_records": self.total_records,
            "downvote_count": self.downvote_count,
            "upvote_count": self.upvote_count,
            "rules": [r.to_dict() for r in self.rules],
            "stopped_reason": self.stopped_reason,
            "llm_model": self.llm_model,
        }


_SYSTEM_PROMPT = (
    "You are a writing-quality analyst reading batches of reader feedback for "
    "AI-generated visual novels. Your job: distill actionable RULES that a "
    "dialogue-writing model should follow to avoid the mistakes readers complain "
    "about and preserve what they praise.\n\n"
    "Constraints:\n"
    "- Output rules that are CONCRETE and TESTABLE. `Avoid overly long monologues` "
    "  is fine; `Be a good writer` is not.\n"
    "- Prefer negative rules (avoid X) when readers complained; positive rules "
    "  (prefer Y) only when up-votes give consistent signal.\n"
    "- Never invent complaints readers didn't raise.\n"
    "- Keep each rule under 30 words.\n"
    "- Output MUST be valid JSON in the schema you're given."
)


def _build_user_prompt(down_reasons: list[str], up_reasons: list[str], max_rules: int) -> str:
    """Compose the batch prompt. Reasons are trimmed for token bound but
    counted so the model knows the sample weight behind each cluster."""
    def _fmt(bucket: list[str]) -> str:
        return "\n".join(f"- {r}" for r in bucket[:200]) or "(none)"

    return (
        f"Read the {len(down_reasons)} DOWN-vote reasons and {len(up_reasons)} UP-vote "
        f"reasons below. Extract 5 to {max_rules} rules the Writer agent should follow.\n\n"
        f"## DOWN-vote reasons ({len(down_reasons)})\n{_fmt(down_reasons)}\n\n"
        f"## UP-vote reasons ({len(up_reasons)})\n{_fmt(up_reasons)}\n\n"
        f"Return JSON with exactly this shape:\n"
        f'{{ "rules": [\n'
        f'    {{"text": "<rule ≤30 words>", "polarity": "avoid" | "prefer", '
        f'      "confidence": <0.0-1.0>, "source_count": <int>}}\n'
        f"  ]\n"
        f"}}\n"
        f"No prose, no commentary — just the JSON object."
    )


def _extract_rules_json(raw: str) -> list[dict]:
    """Parse the LLM output. Tolerant to trailing prose / code fences."""
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    rules = data.get("rules") or []
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict) and r.get("text")]


async def run_reflection(
    *,
    min_samples: int = _DEFAULT_MIN_SAMPLES,
    max_rules: int = _DEFAULT_MAX_RULES,
    force: bool = False,
    llm=None,
    write: bool = True,
) -> ReflectionReport:
    """Read every feedback record, extract rules, write dynamic_guidelines.json.

    Args:
        min_samples: skip when total records < this (unless force=True).
        max_rules: hard cap on emitted rules regardless of LLM output.
        force: bypass the min_samples gate.
        llm: injectable LLM callable for tests. Signature matches ainvoke_llm:
            async (system, user, model=..., caller=...) → message-like.
        write: when False, return report without touching disk.
    """
    records = fb_store.load_all()
    down_reasons = [r.reason.strip() for r in records if r.verdict == "down" and (r.reason or "").strip()]
    up_reasons = [r.reason.strip() for r in records if r.verdict == "up" and (r.reason or "").strip()]

    report = ReflectionReport(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        total_records=len(records),
        downvote_count=sum(1 for r in records if r.verdict == "down"),
        upvote_count=sum(1 for r in records if r.verdict == "up"),
    )

    if len(records) < min_samples and not force:
        report.stopped_reason = "insufficient_samples"
        return report

    if not down_reasons and not up_reasons:
        report.stopped_reason = "no_reasons"
        return report

    # Model resolution mirrors config.py's summarizer default (Haiku-class).
    try:
        from vn_agent.config import get_settings
        model = getattr(get_settings(), "llm_summarizer_model", None) or "claude-haiku-4-5-20251001"
    except Exception:  # noqa: BLE001
        model = "claude-haiku-4-5-20251001"
    report.llm_model = model

    if llm is None:
        from vn_agent.services.llm import ainvoke_llm as _ainvoke
        llm = _ainvoke

    user = _build_user_prompt(down_reasons, up_reasons, max_rules)
    try:
        response = await llm(_SYSTEM_PROMPT, user, model=model, caller="feedback/reflection")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Reflection LLM call failed: {e}")
        report.stopped_reason = "llm_failed"
        return report

    content = getattr(response, "content", response) if not isinstance(response, str) else response
    parsed = _extract_rules_json(str(content))
    if not parsed:
        report.stopped_reason = "llm_failed"
        return report

    for raw in parsed[:max_rules]:
        try:
            g = Guideline(
                text=str(raw["text"]).strip()[:400],
                polarity="prefer" if raw.get("polarity") == "prefer" else "avoid",
                confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.5)))),
                source_count=int(raw.get("source_count", 0)),
                example_ids=list(raw.get("example_ids") or []),
            )
        except (TypeError, ValueError):
            continue
        if g.text:
            report.rules.append(g)

    report.stopped_reason = "ok"

    if write and report.rules:
        _write_atomic(report)

    return report


def _write_atomic(report: ReflectionReport) -> None:
    path = _guidelines_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_guidelines() -> ReflectionReport | None:
    """Read the current dynamic_guidelines.json. Returns None on missing/corrupt."""
    path = _guidelines_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning(f"dynamic_guidelines.json is corrupt: {e}")
        return None
    rules = [
        Guideline(
            text=str(r.get("text", "")).strip(),
            polarity=str(r.get("polarity", "avoid")),
            confidence=float(r.get("confidence", 0.5)),
            source_count=int(r.get("source_count", 0)),
            example_ids=list(r.get("example_ids") or []),
        )
        for r in (data.get("rules") or [])
        if isinstance(r, dict) and r.get("text")
    ]
    return ReflectionReport(
        generated_at=str(data.get("generated_at", "")),
        total_records=int(data.get("total_records", 0)),
        downvote_count=int(data.get("downvote_count", 0)),
        upvote_count=int(data.get("upvote_count", 0)),
        rules=rules,
        stopped_reason=str(data.get("stopped_reason", "")),
        llm_model=str(data.get("llm_model", "")),
    )


def format_guidelines_for_prompt(report: ReflectionReport | None) -> str:
    """Render as a Writer-prompt-ready block. Empty string when no rules.

    Grouped by polarity so Sonnet reads it as a compact directive:
      GUIDELINES (from past reader feedback):
      Avoid:
      - ...
      Prefer:
      - ...
    """
    if not report or not report.rules:
        return ""
    avoid = [r for r in report.rules if r.polarity != "prefer"]
    prefer = [r for r in report.rules if r.polarity == "prefer"]
    lines = ["GUIDELINES (distilled from past reader feedback):"]
    if avoid:
        lines.append("Avoid:")
        for r in avoid:
            lines.append(f"- {r.text}")
    if prefer:
        lines.append("Prefer:")
        for r in prefer:
            lines.append(f"- {r.text}")
    return "\n".join(lines)


# ------- CLI entry ----------------------------------------------------------

def cli_reflect(min_samples: int, max_rules: int, force: bool, dry_run: bool) -> int:
    """Run reflection from the CLI wrapper (see cli.py)."""
    report = asyncio.run(run_reflection(
        min_samples=min_samples,
        max_rules=max_rules,
        force=force,
        write=not dry_run,
    ))
    from rich.console import Console
    console = Console()
    console.print(
        f"[cyan]reflection → {report.stopped_reason}[/cyan] · "
        f"records={report.total_records} (up={report.upvote_count} down={report.downvote_count}) · "
        f"rules={len(report.rules)}"
    )
    for r in report.rules:
        polarity = "🚫" if r.polarity == "avoid" else "✅"
        console.print(f"  {polarity} ({r.confidence:.2f}) {r.text}")
    if report.stopped_reason == "insufficient_samples":
        console.print(f"[yellow]  Need ≥ {min_samples} records; got {report.total_records}. Use --force to override.[/yellow]")
    return 0 if report.rules or report.stopped_reason == "insufficient_samples" else 1
