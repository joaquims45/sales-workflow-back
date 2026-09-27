"""Decision model abstraction for message routing (ARCHITECTURE.md §11).

This is the routing *skeleton*: it defines the contract the real Jev
integration will implement next, wired behind `get_decision_model()` so the
router (and everything upstream of it) never depends on Jev directly.

The default implementation always returns CONTINUE. It exists so the router
pipe can be exercised end-to-end before Jev is integrated — SIDE_QUERY and
REPLACE have no workflow to act on yet (that's M7/M8), so always continuing
is the correct behavior for now, not a shortcut.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from workflows.graph.state import RoutingDecision, SalesState


class RoutingResult(TypedDict):
    decision: str
    confidence: float


class DecisionModel(Protocol):
    def decide(self, message_text: str, state: SalesState) -> RoutingResult: ...


class AlwaysContinueDecisionModel:
    """Placeholder decision model — replaced by Jev in the next milestone."""

    def decide(self, message_text: str, state: SalesState) -> RoutingResult:
        return {"decision": RoutingDecision.CONTINUE, "confidence": 1.0}


def get_decision_model() -> DecisionModel:
    return AlwaysContinueDecisionModel()
