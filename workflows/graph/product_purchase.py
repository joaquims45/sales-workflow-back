"""PRODUCT_PURCHASE workflow graph.

DISCOVERY -> PRODUCT_SEARCH -> RECOMMENDATION -> SELECT_PRODUCT -> CHECKOUT,
with short-circuits back to the user whenever information is missing
(budget, or which product to buy). Every message re-enters at DISCOVERY —
there is no cross-turn node pointer yet, only the persisted SalesState
fields (candidate_products, selected_product_id, etc.) that let a later
turn pick up where the conversation left off.

CHECKOUT never creates the Order/Payment itself — it only calls
apps.orders.services.create_checkout_for_product (ARCHITECTURE.md §17/§49).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from apps.catalog.models import Product
from apps.conversations.models import Conversation
from apps.orders.services import InsufficientStock, ProductUnavailable, create_checkout_for_product
from tools.product_tools import ProductConstraints, search_products

from .extraction import extract_budget, extract_needs, extract_purchase_intent
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
    wants_to_buy = extract_purchase_intent(state["incoming_message"])
    has_a_product_in_mind = bool(state["candidate_products"]) or state["selected_product_id"] is not None

    if wants_to_buy and has_a_product_in_mind:
        return "select_product"

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


def _match_candidate_by_name(text: str, candidate_ids: list[int]) -> int | None:
    lowered = text.lower()
    for product in Product.objects.filter(id__in=candidate_ids):
        name_tokens = [token for token in product.name.lower().split() if len(token) > 2]
        if any(token in lowered for token in name_tokens):
            return product.id
    return None


def select_product_node(state: ProductPurchaseGraphState) -> dict:
    if state["selected_product_id"] is not None:
        return {}

    candidates = state["candidate_products"]
    if len(candidates) == 1:
        return {"selected_product_id": candidates[0]}

    matched_id = _match_candidate_by_name(state["incoming_message"], candidates)
    return {"selected_product_id": matched_id}


def route_after_select(state: ProductPurchaseGraphState) -> str:
    return "checkout" if state["selected_product_id"] is not None else "ask_which_product"


def ask_which_product_node(state: ProductPurchaseGraphState) -> dict:
    products = Product.objects.filter(id__in=state["candidate_products"])
    names = ", ".join(product.name for product in products)
    return {"reply": f"¿Cuál de estas opciones querés? {names}"}


def checkout_node(state: ProductPurchaseGraphState) -> dict:
    conversation = Conversation.objects.filter(pk=state["conversation_id"]).first()

    try:
        outcome = create_checkout_for_product(
            product_id=state["selected_product_id"],
            conversation=conversation,
        )
    except ProductUnavailable:
        return {
            "reply": "Ese producto ya no está disponible. ¿Querés ver otra opción?",
            "active_node": "CHECKOUT",
        }
    except InsufficientStock:
        return {
            "reply": "Justo se quedó sin stock ese producto. ¿Querés que te muestre otra opción?",
            "active_node": "CHECKOUT",
        }

    reply = (
        f"¡Listo! Creé tu orden #{outcome.order.id} por ${outcome.order.total}. "
        f"Para completar el pago entrá a {outcome.checkout_result.checkout_url}"
    )
    return {"reply": reply, "active_node": "CHECKOUT", "checkout_ready": True}


def build_product_purchase_graph():
    graph = StateGraph(ProductPurchaseGraphState)

    graph.add_node("discovery", discovery_node)
    graph.add_node("ask_for_budget", ask_for_budget_node)
    graph.add_node("product_search", product_search_node)
    graph.add_node("recommendation", recommendation_node)
    graph.add_node("select_product", select_product_node)
    graph.add_node("ask_which_product", ask_which_product_node)
    graph.add_node("checkout", checkout_node)

    graph.set_entry_point("discovery")
    graph.add_conditional_edges(
        "discovery",
        route_after_discovery,
        {
            "select_product": "select_product",
            "product_search": "product_search",
            "ask_for_budget": "ask_for_budget",
        },
    )
    graph.add_edge("product_search", "recommendation")
    graph.add_edge("ask_for_budget", END)
    graph.add_edge("recommendation", END)
    graph.add_conditional_edges(
        "select_product",
        route_after_select,
        {"checkout": "checkout", "ask_which_product": "ask_which_product"},
    )
    graph.add_edge("ask_which_product", END)
    graph.add_edge("checkout", END)

    return graph.compile()


_PRODUCT_PURCHASE_GRAPH = build_product_purchase_graph()


def run_product_purchase(state: SalesState, message_text: str) -> tuple[SalesState, str]:
    """Run one turn of the PRODUCT_PURCHASE graph and return (new_state, reply)."""

    graph_input: ProductPurchaseGraphState = {**state, "incoming_message": message_text, "reply": ""}
    result = _PRODUCT_PURCHASE_GRAPH.invoke(graph_input)

    new_state: SalesState = {field: result[field] for field in SALES_STATE_FIELDS}
    reply = result.get("reply", "")

    return new_state, reply
