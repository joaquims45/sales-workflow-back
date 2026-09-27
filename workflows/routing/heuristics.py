"""Deterministic keyword checks used to resolve medium-confidence routing
without paying for an LLM escalation (ARCHITECTURE.md §12).

Intentionally narrow: this only recognizes the side queries Sales Workflow
already knows how to handle (shipping today; warranty/returns later). It is
not meant to grow into a general classifier — that's what Jev/the LLM are
for.
"""

from __future__ import annotations

from workflows.graph.state import RoutingDecision

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


def match_known_side_query_keywords(message_text: str) -> str | None:
    lowered = message_text.lower()
    if any(keyword in lowered for keyword in SIDE_QUERY_KEYWORDS):
        return RoutingDecision.SIDE_QUERY
    return None
