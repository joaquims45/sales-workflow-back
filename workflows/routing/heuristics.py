"""Deterministic keyword checks used to resolve medium-confidence routing
without paying for an LLM escalation (ARCHITECTURE.md §12).

Intentionally narrow: this only recognizes the intents Sales Workflow
already knows how to act on (abandon the goal, or ask a known side query —
shipping today, warranty/returns later). It is not meant to grow into a
general classifier — that's what Jev/the LLM are for.
"""

from __future__ import annotations

from workflows.graph.state import RoutingDecision

REPLACE_KEYWORDS = [
    "olvidate",
    "olvídate",
    "olvidemos",
    "mejor busco",
    "mejor quiero",
    "en realidad quiero",
    "cambié de idea",
    "cambie de idea",
    "en vez de eso",
    "quiero otra cosa",
    "ya no quiero",
]

SIDE_QUERY_KEYWORDS = [
    "envío",
    "envio",
    "entrega",
    "garantía",
    "garantia",
    "devolución",
    "devolucion",
    "horario",
    "sucursal",
]


def match_known_intent_keywords(message_text: str) -> str | None:
    """Checked in priority order: REPLACE is a stronger, more explicit signal
    than a side query, so it's checked first to avoid misreading e.g.
    "olvidate del envío, mejor busco un monitor" as SIDE_QUERY."""

    lowered = message_text.lower()

    if any(keyword in lowered for keyword in REPLACE_KEYWORDS):
        return RoutingDecision.REPLACE

    if any(keyword in lowered for keyword in SIDE_QUERY_KEYWORDS):
        return RoutingDecision.SIDE_QUERY

    return None
