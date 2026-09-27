"""Decision model abstraction for message routing (ARCHITECTURE.md §11).

`DecisionModel` is the contract the router depends on; it never talks to
Jev directly. `get_decision_model()` resolves to the real Jev integration
(workflows/routing/jev_router.py) when TYPESAFE_API_KEY is configured, and
to `AlwaysContinueDecisionModel` otherwise — the same resolver pattern used
for `PaymentProvider` (mock by default, real provider behind config).

`AlwaysContinueDecisionModel` defaults to CONTINUE at *medium* confidence
(deliberately below JEV_CONFIDENCE_HIGH) rather than full certainty: the
router's confidence-threshold logic (workflows/routing/router.py) then still
runs the deterministic keyword heuristic on every message, so known side
queries (shipping today) keep working even with zero external credentials.
Only genuinely ambiguous messages fall through to LLM escalation, which is a
no-op by default (see providers/llm.py) and keeps CONTINUE.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from workflows.graph.state import RoutingDecision, SalesState

# Deliberately inside [JEV_CONFIDENCE_LOW, JEV_CONFIDENCE_HIGH) — see module
# docstring. Not calibrated; there is no model behind this fallback.
FALLBACK_CONFIDENCE = 0.7


class RoutingResult(TypedDict):
    decision: str
    confidence: float


class DecisionModel(Protocol):
    def decide(self, message_text: str, state: SalesState) -> RoutingResult: ...


class AlwaysContinueDecisionModel:
    """Fallback decision model used when Jev isn't configured."""

    def decide(self, message_text: str, state: SalesState) -> RoutingResult:
        return {"decision": RoutingDecision.CONTINUE, "confidence": FALLBACK_CONFIDENCE}


def get_decision_model() -> DecisionModel:
    from .jev_router import get_jev_decision_model

    return get_jev_decision_model()
