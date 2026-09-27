"""Hardcoded, deterministic state transition used only to validate SalesState
end-to-end before LangGraph/Jev/LLM routing exists (see M4+).

This is intentionally NOT the real Sales Workflow graph. It exists to prove
that SalesState can be updated and persisted across turns of a conversation.
It will be replaced by the LangGraph-based router and PRODUCT_PURCHASE graph.
"""

from __future__ import annotations

import re

from .state import FunnelStage, PrimaryGoal, SalesState

BUDGET_PATTERN = re.compile(r"\$?\s*([\d]{1,3}(?:[.,]\d{3})+|\d{4,})")

NEED_KEYWORDS = {
    "gaming": ["gamer", "jugar", "juegos"],
    "programming": ["programar", "programaci", "codear", "docker"],
}


def apply_hardcoded_transition(state: SalesState, message_text: str) -> SalesState:
    """Apply a naive, rule-based update to SalesState from a user message.

    This is a placeholder for the real router (Jev) + PRODUCT_PURCHASE graph.
    """

    text = message_text.lower()

    if state["primary_goal"] is None:
        state["primary_goal"] = PrimaryGoal.BUY_PRODUCT
        state["active_workflow"] = "PRODUCT_PURCHASE"
        state["active_node"] = "DISCOVERY"

    for need, keywords in NEED_KEYWORDS.items():
        if any(keyword in text for keyword in keywords) and need not in state["customer_needs"]:
            state["customer_needs"].append(need)

    budget_match = BUDGET_PATTERN.search(text)
    if budget_match:
        raw_value = budget_match.group(1).replace(".", "").replace(",", "")
        state["constraints"]["budget_max"] = int(raw_value)

    if state["funnel_stage"] == FunnelStage.DISCOVERY and (
        state["customer_needs"] or state["constraints"]
    ):
        state["funnel_stage"] = FunnelStage.CONSIDERATION

    return state
