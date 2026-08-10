"""Every graph node must have a user-facing label.

Regression guard: _STEP_LABELS used to cover only 4 of the graph's 10
nodes, so the fallback f"Running {node_name}" leaked internal identifiers
straight into the UI — users saw "Running cross_ref_sync".
"""
from __future__ import annotations

from vn_agent.agents.graph import build_graph
from vn_agent.web.app import _STEP_LABELS

_SENTINELS = {"__start__", "__end__"}


def test_every_graph_node_has_a_step_label():
    graph = build_graph()
    node_names = {n for n in graph.get_graph().nodes if n not in _SENTINELS}
    missing = node_names - set(_STEP_LABELS)
    assert not missing, f"graph nodes without a user-facing label: {sorted(missing)}"


def test_no_label_leaks_an_internal_identifier():
    """A label must read as prose, not as a node id."""
    for node, label in _STEP_LABELS.items():
        assert "_" not in label, f"{node!r} label looks like an identifier: {label!r}"
        assert label[:1].isupper(), f"{node!r} label should start capitalised: {label!r}"
