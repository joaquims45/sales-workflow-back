"""Jev-backed decision model (ARCHITECTURE.md §11).

This talks to TypeSafe's System One API directly via `typesafe_sdk.Choice`,
rather than the higher-level `jev.fn` decorator. `jev.fn` is convenient but
explicitly discards calibrated probabilities/confidence (per its own
documented limitations) — and confidence-gated routing is the entire reason
Sales Workflow uses Jev, so the raw SDK is the right layer here.

Requires Python 3.14+ (a `jev`/`typesafe-sdk` constraint) and a
TYPESAFE_API_KEY. When no key is configured, `get_decision_model()` falls
back to `AlwaysContinueDecisionModel` — same pattern as
MockPaymentProvider — so the project still runs with zero external
credentials by default.
"""

from __future__ import annotations

import logging

from django.conf import settings
from typesafe_sdk import Choice, TypeSafeClient, TypeSafeError

from workflows.graph.state import RoutingDecision, SalesState

from .decision_model import AlwaysContinueDecisionModel, DecisionModel, RoutingResult

logger = logging.getLogger(__name__)

_ROUTING_CRITERIA = {
    RoutingDecision.CONTINUE: (
        "The message continues providing information the active workflow/node asked for, "
        "or otherwise moves the current goal forward."
    ),
    RoutingDecision.SIDE_QUERY: (
        "The message asks about something unrelated to the active node (shipping, warranty, "
        "store hours, etc.) without abandoning the current goal — it expects a quick answer "
        "before returning to what it was doing."
    ),
    RoutingDecision.REPLACE: (
        "The message abandons the current goal entirely and starts pursuing a different one."
    ),
}


class JevDecisionModel:
    """Routes CONTINUE/SIDE_QUERY/REPLACE using TypeSafe System One (Jev)."""

    def __init__(self, client: TypeSafeClient | None = None):
        self._client = client or TypeSafeClient(api_key=settings.TYPESAFE_API_KEY)
        self._fallback = AlwaysContinueDecisionModel()

    def decide(self, message_text: str, state: SalesState) -> RoutingResult:
        try:
            response = self._client.system_one(
                state={
                    "message": message_text,
                    "primary_goal": state["primary_goal"],
                    "active_workflow": state["active_workflow"],
                    "active_node": state["active_node"],
                },
                questions={
                    "routing": Choice(
                        instructions=(
                            "Given the active sales workflow and the customer's new message, "
                            "decide how to route it."
                        ),
                        criteria=_ROUTING_CRITERIA,
                    ),
                },
            )
        except TypeSafeError:
            logger.warning("Jev routing call failed, falling back to CONTINUE.", exc_info=True)
            return self._fallback.decide(message_text, state)

        answer = response.choices["routing"]
        return {"decision": answer.choice, "confidence": answer.confidence}


def get_jev_decision_model() -> DecisionModel:
    """Resolves to Jev when configured, otherwise the CONTINUE-only fallback."""

    if not settings.TYPESAFE_API_KEY:
        return AlwaysContinueDecisionModel()

    try:
        return JevDecisionModel()
    except TypeSafeError:
        logger.warning("Could not initialize the Jev client, falling back to CONTINUE.", exc_info=True)
        return AlwaysContinueDecisionModel()
