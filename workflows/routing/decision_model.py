"""Decision model abstraction for message routing (ARCHITECTURE.md §11).

`DecisionModel` is the contract the router depends on; it never talks to
Jev directly. `get_decision_model()` resolves to the real Jev integration
(workflows/routing/jev_router.py) when TYPESAFE_API_KEY is configured, and
to `AlwaysContinueDecisionModel` otherwise — the same resolver pattern used
for `PaymentProvider` (mock by default, real provider behind config).

`AlwaysContinueDecisionModel` always returning CONTINUE is intentional, not
a shortcut: SIDE_QUERY and REPLACE have no workflow to act on yet
(that lands in M7/M8), so always continuing is the correct behavior for a
project that hasn't configured Jev.
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
    """Fallback decision model used when Jev isn't configured."""

    def decide(self, message_text: str, state: SalesState) -> RoutingResult:
        return {"decision": RoutingDecision.CONTINUE, "confidence": 1.0}


def get_decision_model() -> DecisionModel:
    from .jev_router import get_jev_decision_model

    return get_jev_decision_model()
