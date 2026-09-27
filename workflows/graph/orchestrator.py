"""Suspends the active workflow, runs a side workflow, and resumes
(ARCHITECTURE.md §8-10).

Only SHIPPING_QUERY exists today, so this dispatches to it directly — a
real dispatcher (picking among multiple side workflows from the message)
only earns its place once a second one (e.g. WARRANTY_QUERY) exists.

RESUME is not something the router decides (ARCHITECTURE.md §6): it's the
internal transition this function performs once the side workflow
completes, restoring active_workflow/active_node from workflow_stack.
"""

from __future__ import annotations

from .shipping_query import run_shipping_query
from .state import RoutingDecision, SalesState


def run_side_query(state: SalesState, message_text: str) -> tuple[SalesState, str]:
    previous_workflow = state["active_workflow"]
    previous_node = state["active_node"]

    if previous_workflow is not None:
        state["workflow_stack"] = state["workflow_stack"] + [
            {"workflow": previous_workflow, "node": previous_node}
        ]
    state["suspended_workflow"] = previous_workflow
    state["suspended_node"] = previous_node
    state["interruption"] = "SHIPPING_QUERY"
    state["active_workflow"] = "SHIPPING_QUERY"
    state["active_node"] = "EXTRACT_DESTINATION"

    reply = run_shipping_query(message_text)

    if state["workflow_stack"]:
        frame = state["workflow_stack"][-1]
        state["workflow_stack"] = state["workflow_stack"][:-1]
        state["active_workflow"] = frame["workflow"]
        state["active_node"] = frame["node"]
    else:
        state["active_workflow"] = None
        state["active_node"] = None

    state["suspended_workflow"] = None
    state["suspended_node"] = None
    state["interruption"] = None
    state["routing_decision"] = RoutingDecision.RESUME
    state["routing_confidence"] = 1.0

    return state, reply
