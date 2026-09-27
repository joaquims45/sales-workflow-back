"""Shipping domain tool (ARCHITECTURE.md §16).

Deterministic, fictional shipping zones for the demo catalog — no external
carrier integration. Coverage/cost/lead time are the only things
SHIPPING_QUERY is allowed to know, and only through this tool.
"""

from __future__ import annotations

from dataclasses import dataclass

# destination -> (cost, days). Fictional demo data (ARCHITECTURE.md §37).
SHIPPING_ZONES: dict[str, tuple[int, int]] = {
    "CABA": (6000, 1),
    "Buenos Aires": (8000, 2),
    "Córdoba": (12000, 3),
    "Santa Fe": (12000, 3),
    "Mendoza": (15000, 4),
}


@dataclass
class ShippingQuote:
    destination: str
    cost: int
    days: int


def calculate_shipping(destination: str) -> ShippingQuote | None:
    zone = SHIPPING_ZONES.get(destination)
    if zone is None:
        return None
    cost, days = zone
    return ShippingQuote(destination=destination, cost=cost, days=days)
