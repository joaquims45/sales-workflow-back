"""LLM provider abstraction, scoped to routing escalation for now
(ARCHITECTURE.md §36).

This is deliberately narrow — one method, not a general chat/completions
interface — because routing escalation is the only place a frontier LLM is
invoked so far. A broader AIProvider can grow out of this once agents need
open-ended generation (see MVP agents in ARCHITECTURE.md §13).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from workflows.graph.state import SalesState
    from workflows.routing.decision_model import RoutingResult


class RoutingLLMProvider(Protocol):
    def decide_routing(self, message_text: str, state: "SalesState") -> "RoutingResult | None":
        """Returns a routing decision, or None if escalation isn't available."""
        ...


class NullRoutingLLMProvider:
    """Default provider: no LLM is configured.

    Returns None (cannot escalate) rather than fabricating a decision, so
    the router falls back to Jev's own low-confidence call. This keeps the
    project runnable with zero external LLM credentials by default — wiring
    a real provider (OpenAI/Anthropic/etc.) is a later, separate milestone.
    """

    def decide_routing(self, message_text: str, state: "SalesState") -> "RoutingResult | None":
        return None


def get_routing_llm_provider() -> RoutingLLMProvider:
    return NullRoutingLLMProvider()
