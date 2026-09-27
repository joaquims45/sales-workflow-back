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

# What each active_node is actually asking for — without this, "2 millones"
# or a bare place name look ambiguous to a generic classifier. With it,
# they're obviously a direct answer to the question just asked.
_NODE_EXPECTATIONS = {
    None: "The conversation just started; nothing has been asked yet.",
    "DISCOVERY": "Gathering what the customer wants and their budget. A short answer "
    "(a product type, a number, \"no sé\", etc.) is almost always answering that.",
    "PRODUCT_SEARCH": "Looking up matching products — no question pending.",
    "RECOMMENDATION": "Just showed product options; a short reply likely reacts to them.",
    "CHECKOUT": "Finalizing the purchase.",
    "EXTRACT_DESTINATION": "Just asked which city/town to quote shipping for. A bare place "
    "name (\"Chivilcoy\", \"Santa Fe\") is that answer, not a new topic.",
}

_ROUTING_CRITERIA = {
    RoutingDecision.CONTINUE: (
        "The message answers or moves forward whatever the active node is currently asking "
        "(see active_node's expectation below) — this is the default for short or ambiguous "
        "messages when nothing clearly signals otherwise. Also correct for a greeting at the "
        "very start of the conversation (primary_goal is null) — that is never CHITCHAT."
    ),
    RoutingDecision.CHITCHAT: (
        "The message is a greeting, thanks, acknowledgment, or farewell (e.g. \"hola\", "
        "\"gracias\", \"genial gracias\", \"chau\") that does not answer what the active node is "
        "currently asking and does not raise a new topic or abandon the goal — it's purely "
        "conversational. IMPORTANT: only valid when primary_goal is not null (a goal is already "
        "in progress or completed). If primary_goal is null, a greeting like \"hola\" is the "
        "conversation just starting — choose CONTINUE instead, never CHITCHAT."
    ),
    RoutingDecision.SIDE_QUERY: (
        "The message explicitly asks about a different, recognizable topic (shipping, warranty, "
        "store hours, etc.) than what the active node is asking, without abandoning the current "
        "goal — it expects a quick answer before returning to what it was doing. Do not choose "
        "this just because a message is short or a bare answer (a place name, a number)."
    ),
    RoutingDecision.REPLACE: (
        "The message explicitly abandons the current goal and states a different one "
        "(e.g. \"olvidate de eso, mejor quiero...\"). Do not choose this for a plain answer to "
        "the current question."
    ),
}


class JevDecisionModel:
    """Routes CONTINUE/SIDE_QUERY/REPLACE using TypeSafe System One (Jev)."""

    def __init__(self, client: TypeSafeClient | None = None):
        self._client = client or TypeSafeClient(api_key=settings.TYPESAFE_API_KEY)
        self._fallback = AlwaysContinueDecisionModel()

    def decide(self, message_text: str, state: SalesState) -> RoutingResult:
        active_node = state["active_node"]
        try:
            response = self._client.system_one(
                state={
                    "message": message_text,
                    "primary_goal": state["primary_goal"],
                    "active_workflow": state["active_workflow"],
                    "active_node": active_node,
                    "what_active_node_is_asking": _NODE_EXPECTATIONS.get(
                        active_node, "Continuing the active workflow."
                    ),
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
