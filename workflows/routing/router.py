"""Routes an incoming message against the current SalesState.

Confidence strategy (ARCHITECTURE.md §12):
- high confidence: trust Jev's decision as-is.
- medium confidence: try a cheap deterministic keyword check before paying
  for an LLM call; use it if it resolves the ambiguity, else escalate.
- low confidence: escalate straight to an LLM.

This module only decides; acting on the decision (suspending for
SIDE_QUERY, resetting for REPLACE) happens in
workflows/graph/orchestrator.py.
"""

from __future__ import annotations

import logging

from django.conf import settings

from providers.llm import get_routing_llm_provider
from workflows.graph.state import SalesState

from .decision_model import DecisionModel, RoutingResult, get_decision_model
from .heuristics import match_known_intent_keywords

logger = logging.getLogger(__name__)


def route_message(
    state: SalesState, message_text: str, decision_model: DecisionModel | None = None
) -> tuple[SalesState, RoutingResult]:
    """Returns (state, raw_decision) — raw_decision is Jev's call before
    thresholds/heuristics/escalation, so callers can emit `jev.decision`
    separately from the final `routing.completed` (ARCHITECTURE.md §20)."""

    model = decision_model or get_decision_model()
    raw_result = model.decide(message_text, state)
    final_result = _resolve_with_confidence(message_text, state, raw_result)

    state["routing_decision"] = final_result["decision"]
    state["routing_confidence"] = final_result["confidence"]

    return state, raw_result


def _resolve_with_confidence(message_text: str, state: SalesState, result: RoutingResult) -> RoutingResult:
    if result["confidence"] >= settings.JEV_CONFIDENCE_HIGH:
        return result

    if result["confidence"] >= settings.JEV_CONFIDENCE_LOW:
        keyword_decision = match_known_intent_keywords(message_text)
        if keyword_decision is not None:
            logger.info("Resolved medium-confidence routing via keyword heuristic: %s", keyword_decision)
            return {"decision": keyword_decision, "confidence": result["confidence"]}

    logger.info("Escalating routing decision to LLM (confidence=%.2f).", result["confidence"])
    escalated = get_routing_llm_provider().decide_routing(message_text, state)
    if escalated is not None:
        return escalated

    logger.info("No LLM escalation available, keeping Jev's low-confidence decision.")
    return result
