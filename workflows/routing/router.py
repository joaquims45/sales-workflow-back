"""Routes an incoming message against the current SalesState.

For now this only records the decision (see decision_model.py) — acting on
SIDE_QUERY (suspend/resume) and REPLACE (close/replace goal) lands in
M7/M8. Until then every conversation is driven by CONTINUE, which is also
what the decision model always returns.
"""

from __future__ import annotations

from workflows.graph.state import SalesState

from .decision_model import get_decision_model


def route_message(state: SalesState, message_text: str) -> SalesState:
    model = get_decision_model()
    result = model.decide(message_text, state)

    state["routing_decision"] = result["decision"]
    state["routing_confidence"] = result["confidence"]

    return state
