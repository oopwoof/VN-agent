"""Trace context and span timing for pipeline observability."""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """A timed span within a trace."""

    name: str
    start_time: float = 0.0
    end_time: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration_s": round(self.duration_s, 3),
            "attributes": self.attributes,
        }


class SpanContext:
    """Context manager for timing a span."""

    def __init__(self, span: Span):
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        self._span.attributes[key] = value

    def __enter__(self) -> SpanContext:
        self._span.start_time = time.monotonic()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._span.end_time = time.monotonic()


class TraceContext:
    """Collects spans for a single pipeline run."""

    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or uuid.uuid4().hex[:12]
        self.spans: list[Span] = []
        self._start_time = time.monotonic()

    def span(self, name: str) -> SpanContext:
        """Create a new span context manager."""
        s = Span(name=name)
        self.spans.append(s)
        return SpanContext(s)

    @property
    def total_duration_s(self) -> float:
        return time.monotonic() - self._start_time

    def summary(self) -> str:
        """Format a human-readable trace summary."""
        lines = [f"Trace {self.trace_id} ({self.total_duration_s:.1f}s total)"]
        for s in self.spans:
            tokens = ""
            if "input_tokens" in s.attributes or "output_tokens" in s.attributes:
                t_in = s.attributes.get("input_tokens", 0)
                t_out = s.attributes.get("output_tokens", 0)
                tokens = f"  {t_in:,} in / {t_out:,} out"
            lines.append(f"  {s.name:<25} {s.duration_s:>5.1f}s{tokens}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "total_duration_s": round(self.total_duration_s, 3),
            "spans": [s.to_dict() for s in self.spans],
        }

    def save(self, output_dir: str | Path) -> Path:
        """Save trace as JSON to output_dir/trace.json."""
        path = Path(output_dir) / "trace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


# Module-level singleton (similar to TokenTracker pattern)
_current_trace: TraceContext | None = None


def get_trace() -> TraceContext:
    """Get or create the current trace context."""
    global _current_trace
    if _current_trace is None:
        _current_trace = TraceContext()
    return _current_trace


def reset_trace(trace_id: str | None = None) -> TraceContext:
    """Reset the global trace context (call at start of pipeline)."""
    global _current_trace
    _current_trace = TraceContext(trace_id)
    return _current_trace
