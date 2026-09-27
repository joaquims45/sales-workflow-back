"""SHIPPING_QUERY side workflow (ARCHITECTURE.md §13).

ExtractDestination -> ValidateDestination -> CalculateShipping ->
GenerateAnswer. RESUME is not a node here — it's the orchestrator's job
(workflows/graph/orchestrator.py) once this graph returns its reply.

This graph has its own small, transient state — it never touches
SalesState directly, so a side query can't corrupt the suspended main
workflow (ARCHITECTURE.md §7).
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from providers.reply import generate_reply
from tools.shipping_tools import SHIPPING_ZONES, calculate_shipping


class ShippingQueryState(TypedDict):
    incoming_message: str
    destination: str | None
    is_serviceable: bool
    shipping_cost: int | None
    shipping_days: int | None
    reply: str


def extract_destination_node(state: ShippingQueryState) -> dict:
    text = state["incoming_message"].lower()
    for destination in SHIPPING_ZONES:
        if destination.lower() in text:
            return {"destination": destination}
    return {"destination": None}


def route_after_extract(state: ShippingQueryState) -> str:
    return "validate_destination" if state["destination"] else "ask_for_destination"


def ask_for_destination_node(state: ShippingQueryState) -> dict:
    reply = generate_reply(
        "Ask which city/town to calculate shipping cost for.",
        {},
        "¿A qué localidad querés que te cotice el envío?",
    )
    return {"reply": reply}


def validate_destination_node(state: ShippingQueryState) -> dict:
    quote = calculate_shipping(state["destination"])
    return {"is_serviceable": quote is not None}


def route_after_validate(state: ShippingQueryState) -> str:
    return "calculate_shipping" if state["is_serviceable"] else "not_serviceable"


def not_serviceable_node(state: ShippingQueryState) -> dict:
    reply = generate_reply(
        "We don't ship to this destination yet. Apologize briefly.",
        {"destination": state["destination"]},
        f"Por ahora no hacemos envíos a {state['destination']}.",
    )
    return {"reply": reply}


def calculate_shipping_node(state: ShippingQueryState) -> dict:
    quote = calculate_shipping(state["destination"])
    return {"shipping_cost": quote.cost, "shipping_days": quote.days}


def generate_answer_node(state: ShippingQueryState) -> dict:
    fallback = (
        f"Sí, hacemos envíos a {state['destination']}. "
        f"Tarda {state['shipping_days']} día(s) hábiles y cuesta ${state['shipping_cost']}."
    )
    facts = {
        "destination": state["destination"],
        "cost": state["shipping_cost"],
        "days": state["shipping_days"],
    }
    reply = generate_reply(
        "Confirm we ship to this destination, stating the cost and delivery time.",
        facts,
        fallback,
    )
    return {"reply": reply}


def build_shipping_query_graph():
    graph = StateGraph(ShippingQueryState)

    graph.add_node("extract_destination", extract_destination_node)
    graph.add_node("ask_for_destination", ask_for_destination_node)
    graph.add_node("validate_destination", validate_destination_node)
    graph.add_node("not_serviceable", not_serviceable_node)
    graph.add_node("calculate_shipping", calculate_shipping_node)
    graph.add_node("generate_answer", generate_answer_node)

    graph.set_entry_point("extract_destination")
    graph.add_conditional_edges(
        "extract_destination",
        route_after_extract,
        {"validate_destination": "validate_destination", "ask_for_destination": "ask_for_destination"},
    )
    graph.add_conditional_edges(
        "validate_destination",
        route_after_validate,
        {"calculate_shipping": "calculate_shipping", "not_serviceable": "not_serviceable"},
    )
    graph.add_edge("ask_for_destination", END)
    graph.add_edge("not_serviceable", END)
    graph.add_edge("calculate_shipping", "generate_answer")
    graph.add_edge("generate_answer", END)

    return graph.compile()


_SHIPPING_QUERY_GRAPH = build_shipping_query_graph()


def run_shipping_query(message_text: str) -> tuple[str, bool]:
    """Returns (reply, resolved).

    resolved=False only when the message had no usable destination and the
    graph had to ask for one — the caller (workflows/graph/orchestrator.py)
    uses this to keep the conversation suspended in SHIPPING_QUERY instead
    of resuming, so the next message (the actual destination) comes back
    here instead of being routed as if nothing was pending.
    """

    result = _SHIPPING_QUERY_GRAPH.invoke(
        {
            "incoming_message": message_text,
            "destination": None,
            "is_serviceable": False,
            "shipping_cost": None,
            "shipping_days": None,
            "reply": "",
        }
    )
    return result["reply"], result["destination"] is not None
