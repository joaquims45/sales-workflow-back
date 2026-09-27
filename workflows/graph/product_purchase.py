"""PRODUCT_PURCHASE workflow graph (happy path).

Nodes: DISCOVERY -> PRODUCT_SEARCH -> RECOMMENDATION, with a short-circuit
back to the user when there isn't enough information yet (no budget).

No routing (CONTINUE/SIDE_QUERY/REPLACE) and no Jev/LLM here yet — every
message runs this same graph from DISCOVERY. That lands in M6+.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from apps.catalog.models import Product
from tools.product_tools import ProductConstraints, search_products

from .extraction import extract_budget, extract_needs
from .state import FunnelStage, PrimaryGoal, SalesState

SALES_STATE_FIELDS = tuple(SalesState.__annotations__.keys())


class ProductPurchaseGraphState(SalesState):
    incoming_message: str
    reply: str


def discovery_node(state: ProductPurchaseGraphState) -> dict:
    updates: dict = {"active_node": "DISCOVERY"}

    if state["primary_goal"] is None:
        updates["primary_goal"] = PrimaryGoal.BUY_PRODUCT
        updates["active_workflow"] = "PRODUCT_PURCHASE"

    text = state["incoming_message"]

    needs = list(state["customer_needs"])
    for need in extract_needs(text):
        if need not in needs:
            needs.append(need)
    updates["customer_needs"] = needs

    constraints = dict(state["constraints"])
    budget = extract_budget(text)
    if budget is not None:
        constraints["budget_max"] = budget
    updates["constraints"] = constraints

    if state["funnel_stage"] == FunnelStage.DISCOVERY and (needs or constraints):
        updates["funnel_stage"] = FunnelStage.CONSIDERATION

    return updates


def route_after_discovery(state: ProductPurchaseGraphState) -> str:
    return "product_search" if state["constraints"].get("budget_max") is not None else "ask_for_budget"


def ask_for_budget_node(state: ProductPurchaseGraphState) -> dict:
    if state["customer_needs"]:
        reply = "¿Qué presupuesto tenés?"
    else:
        reply = "Contame qué estás buscando y con qué presupuesto contás."
    return {"reply": reply}


def product_search_node(state: ProductPurchaseGraphState) -> dict:
    constraints = ProductConstraints(
        budget_max=state["constraints"].get("budget_max"),
        needs=state["customer_needs"],
    )
    query = " ".join(state["customer_needs"] + [state["incoming_message"]]).strip()
    candidates = search_products(query, constraints)
    return {"candidate_products": [candidate.id for candidate in candidates], "active_node": "PRODUCT_SEARCH"}


def recommendation_node(state: ProductPurchaseGraphState) -> dict:
    ids = state["candidate_products"]
    if not ids:
        reply = (
            "No encontré productos que cumplan esas condiciones. "
            "¿Querés ajustar el presupuesto o contarme más sobre lo que buscás?"
        )
        return {"reply": reply, "active_node": "RECOMMENDATION"}

    products_by_id = {product.id: product for product in Product.objects.filter(id__in=ids)}
    ordered = [products_by_id[product_id] for product_id in ids if product_id in products_by_id]

    lines = [f"- {product.name} (${product.price}) — {', '.join(product.use_cases)}" for product in ordered]
    reply = "Encontré estas opciones para vos:\n" + "\n".join(lines)

    return {"reply": reply, "active_node": "RECOMMENDATION"}


def build_product_purchase_graph():
    graph = StateGraph(ProductPurchaseGraphState)

    graph.add_node("discovery", discovery_node)
    graph.add_node("ask_for_budget", ask_for_budget_node)
    graph.add_node("product_search", product_search_node)
    graph.add_node("recommendation", recommendation_node)

    graph.set_entry_point("discovery")
    graph.add_conditional_edges(
        "discovery",
        route_after_discovery,
        {"product_search": "product_search", "ask_for_budget": "ask_for_budget"},
    )
    graph.add_edge("product_search", "recommendation")
    graph.add_edge("ask_for_budget", END)
    graph.add_edge("recommendation", END)

    return graph.compile()


_PRODUCT_PURCHASE_GRAPH = build_product_purchase_graph()


def run_product_purchase(state: SalesState, message_text: str) -> tuple[SalesState, str]:
    """Run one turn of the PRODUCT_PURCHASE graph and return (new_state, reply)."""

    graph_input: ProductPurchaseGraphState = {**state, "incoming_message": message_text, "reply": ""}
    result = _PRODUCT_PURCHASE_GRAPH.invoke(graph_input)

    new_state: SalesState = {field: result[field] for field in SALES_STATE_FIELDS}
    reply = result.get("reply", "")

    return new_state, reply
