"""v4 P0-review-hang: pending-debug + timeout wrapper for reviewer LLM calls.

Context: job 3cbbf260 (real Sonnet, text_only) hung for 52 minutes on the
Reviewer node with **zero on-disk artifacts** — no debug file, no partial
response, no trace event. The salvage utility recovered the Writer output
but the Reviewer hang itself remained un-diagnosable after the fact.

This helper solves two things at once:

1. **Pending flush.** Before every wrapped LLM call, write a
   `debug/{name}.pending.txt` with the prompt, model, caller tag, and
   UTC timestamp. On success we unlink it (or optionally rename to
   `.done.txt`); on exception we rename to `.error.txt` with the traceback.
   A file with `.pending.txt` still on disk = a call that hasn't returned
   → operators can grep for it and know exactly which prompt is stuck.

2. **Hard timeout.** `asyncio.wait_for(..., timeout)` around the LLM
   call means Reviewer / StructureReviewer can't hang the whole pipeline
   forever. Defaults come from `settings.reviewer_timeout_seconds` (300s)
   so the number is tunable per environment.

The wrapper is a thin drop-in for `ainvoke_llm`; callers pass their own
output_dir + descriptive name and get back exactly what `ainvoke_llm`
would have returned.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_DEFAULT_TIMEOUT_SEC = 300.0     # 5 min — generous for a Sonnet reviewer round
_HEADER_SEP = "\n" + "=" * 40 + "\n"


def _pending_path(output_dir: str | Path, name: str) -> Path:
    """`{output_dir}/debug/{name}.pending.txt` (parents created lazily on write)."""
    return Path(output_dir) / "debug" / f"{name}.pending.txt"


def _serialize_pending(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None,
    caller: str,
    timeout: float,
    schema_name: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header_lines = [
        f"[PENDING] issued at {now}",
        f"caller: {caller}",
        f"model: {model or '(pipeline default)'}",
        f"timeout: {timeout:.1f}s",
    ]
    if schema_name:
        header_lines.append(f"schema: {schema_name}")
    header = "\n".join(header_lines)
    return (
        f"{header}"
        f"{_HEADER_SEP}## SYSTEM PROMPT ##\n{system_prompt}"
        f"{_HEADER_SEP}## USER PROMPT ##\n{user_prompt}"
        f"{_HEADER_SEP}"
    )


def _write_pending(path: Path, body: str) -> None:
    """Best-effort write; failure is logged, never re-raised."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    except OSError as e:
        logger.debug(f"pending-debug write failed at {path}: {e}")


def _finalize_success(path: Path, response_content: str) -> None:
    """Delete the pending marker; write a .txt companion with the raw response.

    We keep the raw response so callers who used to rely on the older
    Director-style `_save_debug_raw` pattern still have their audit file.
    """
    done_path = path.with_name(path.name.replace(".pending.txt", ".txt"))
    try:
        done_path.write_text(response_content, encoding="utf-8")
    except OSError as e:
        logger.debug(f"pending-debug done-write failed at {done_path}: {e}")
    try:
        path.unlink()
    except OSError:
        pass


def _finalize_error(path: Path, exc: BaseException) -> None:
    """Rename pending → error, appending traceback. Never re-raises."""
    err_path = path.with_name(path.name.replace(".pending.txt", ".error.txt"))
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        err_body = (
            f"{existing}\n{_HEADER_SEP}## ERROR ##\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"{traceback.format_exception(type(exc), exc, exc.__traceback__)}\n"
        )
        err_path.write_text("".join(err_body) if isinstance(err_body, list) else err_body, encoding="utf-8")
    except OSError as e:
        logger.debug(f"pending-debug error-rename failed at {err_path}: {e}")
    try:
        path.unlink()
    except OSError:
        pass


async def ainvoke_with_pending_debug(
    system_prompt: str,
    user_prompt: str,
    *,
    output_dir: str | Path,
    name: str,
    schema: type[T] | None = None,
    model: str | None = None,
    caller: str = "llm",
    timeout: float | None = None,
    **llm_kwargs,
) -> T | str:
    """Call `services.llm.ainvoke_llm` with pending-debug + hard timeout.

    Args:
        output_dir: pipeline run's on-disk root; pending file lands under
                    `{output_dir}/debug/{name}.pending.txt`.
        name: stable, filesystem-safe slug (e.g. "reviewer_round1",
              "structure_reviewer_pass2"). Reused across pending/done/error
              triplet.
        timeout: seconds before we abort. None → read
                 `settings.reviewer_timeout_seconds`, falling back to 300.
        schema, model, caller, **llm_kwargs: forwarded to `ainvoke_llm`.

    Returns whatever `ainvoke_llm` returns. On timeout, raises
    `asyncio.TimeoutError`; the pending file becomes `.error.txt`
    so a next-run analyzer can see WHICH call failed.
    """
    from vn_agent.services.llm import ainvoke_llm

    if timeout is None:
        try:
            from vn_agent.config import get_settings
            timeout = float(getattr(get_settings(), "reviewer_timeout_seconds", _DEFAULT_TIMEOUT_SEC))
        except Exception:  # noqa: BLE001
            timeout = _DEFAULT_TIMEOUT_SEC

    schema_name = schema.__name__ if schema is not None else None
    pending_path = _pending_path(output_dir, name)
    _write_pending(
        pending_path,
        _serialize_pending(
            system_prompt, user_prompt,
            model=model, caller=caller, timeout=timeout,
            schema_name=schema_name,
        ),
    )

    try:
        result = await asyncio.wait_for(
            ainvoke_llm(
                system_prompt, user_prompt,
                schema=schema, model=model, caller=caller,
                **llm_kwargs,
            ),
            timeout=timeout,
        )
    except BaseException as e:
        _finalize_error(pending_path, e)
        raise
    else:
        try:
            content = getattr(result, "content", None)
            if content is None:
                content = str(result)
        except Exception:  # noqa: BLE001
            content = "(response object had no serializable content)"
        _finalize_success(pending_path, str(content))
        return result


def pending_files(output_dir: str | Path) -> list[Path]:
    """List every `.pending.txt` under output_dir/debug — for run-analyzer + smoke tests."""
    debug = Path(output_dir) / "debug"
    if not debug.exists():
        return []
    return sorted(debug.glob("*.pending.txt"))
