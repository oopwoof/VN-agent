"""Tests for the tracing / observability system."""
from __future__ import annotations

import json
import time

from vn_agent.observability.tracing import Span, SpanContext, TraceContext, get_trace, reset_trace


class TestSpan:
    def test_duration_calculation(self):
        s = Span(name="test", start_time=1.0, end_time=3.5)
        assert s.duration_s == 2.5

    def test_zero_duration_when_not_set(self):
        s = Span(name="test")
        assert s.duration_s == 0.0

    def test_to_dict(self):
        s = Span(name="my_span", start_time=1.0, end_time=2.0, attributes={"key": "val"})
        d = s.to_dict()
        assert d["name"] == "my_span"
        assert d["duration_s"] == 1.0
        assert d["attributes"]["key"] == "val"


class TestSpanContext:
    def test_context_manager_sets_times(self):
        s = Span(name="test")
        ctx = SpanContext(s)
        with ctx:
            time.sleep(0.05)
        assert s.start_time > 0
        assert s.end_time >= s.start_time
        assert s.duration_s >= 0

    def test_set_attribute(self):
        s = Span(name="test")
        ctx = SpanContext(s)
        with ctx as c:
            c.set_attribute("tokens", 100)
        assert s.attributes["tokens"] == 100


class TestTraceContext:
    def test_create_span(self):
        trace = TraceContext(trace_id="test123")
        with trace.span("director") as s:
            s.set_attribute("input_tokens", 500)
        assert len(trace.spans) == 1
        assert trace.spans[0].name == "director"
        assert trace.spans[0].attributes["input_tokens"] == 500

    def test_multiple_spans(self):
        trace = TraceContext()
        with trace.span("step1"):
            pass
        with trace.span("step2"):
            pass
        assert len(trace.spans) == 2

    def test_trace_id_auto_generated(self):
        trace = TraceContext()
        assert len(trace.trace_id) == 12

    def test_trace_id_custom(self):
        trace = TraceContext(trace_id="custom_id")
        assert trace.trace_id == "custom_id"

    def test_total_duration(self):
        trace = TraceContext()
        time.sleep(0.05)
        assert trace.total_duration_s >= 0

    def test_summary_format(self):
        trace = TraceContext(trace_id="abc123")
        with trace.span("director") as s:
            s.set_attribute("input_tokens", 1200)
            s.set_attribute("output_tokens", 800)
        summary = trace.summary()
        assert "abc123" in summary
        assert "director" in summary
        assert "1,200 in" in summary

    def test_to_dict(self):
        trace = TraceContext(trace_id="test")
        with trace.span("step"):
            pass
        d = trace.to_dict()
        assert d["trace_id"] == "test"
        assert len(d["spans"]) == 1
        assert "total_duration_s" in d

    def test_save_to_file(self, tmp_path):
        trace = TraceContext(trace_id="save_test")
        with trace.span("writer"):
            pass
        path = trace.save(tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["trace_id"] == "save_test"
        assert len(data["spans"]) == 1


class TestModuleSingleton:
    def test_reset_creates_new_trace(self):
        t1 = reset_trace("first")
        t2 = reset_trace("second")
        assert t1.trace_id == "first"
        assert t2.trace_id == "second"
        assert get_trace().trace_id == "second"

    def test_get_trace_creates_if_needed(self):
        from vn_agent.observability import tracing
        tracing._current_trace = None
        t = get_trace()
        assert t is not None
        assert len(t.trace_id) == 12
