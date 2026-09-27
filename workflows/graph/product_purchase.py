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
from providers.discovery import get_discovery_extraction_provider
from providers.reply import generate_reply
from tools.product_tools import ProductConstraints, search_products

from .extraction import extract_budget, extract_needs, extract_purchase_intent
from .instrumentation import instrument
from .state import FunnelStage, PrimaryGoal, SalesState

SALES_STATE_FIELDS = tuple(SalesState.__annotations__.keys())


class ProductPurchaseGraphState(SalesState):
    incoming_message: str
    reply: str
    budget_unknown: bool
    wants_to_buy: bool


def discovery_node(state: ProductPurchaseGraphState) -> dict:
    updates: dict = {"active_node": "DISCOVERY", "budget_unknown": False, "wants_to_buy": False}

    if state["primary_goal"] is None:
        updates["primary_goal"] = PrimaryGoal.BUY_PRODUCT
        updates["active_workflow"] = "PRODUCT_PURCHASE"

    text = state["incoming_message"]
    needs = list(state["customer_needs"])
    constraints = dict(state["constraints"])

    # Uses OpenAI when configured (understands free-form needs and "I don't
    # know my budget"); falls back to the deterministic keyword extraction
    # below otherwise (providers/discovery.py).
    extraction = get_discovery_extraction_provider().extract(text, state)

    if extraction is not None:
        for need in extraction["needs"]:
            if need not in needs:
                needs.append(need)
        if extraction["budget_max"] is not None:
            constraints["budget_max"] = extraction["budget_max"]
        updates["budget_unknown"] = extraction["budget_unknown"]
        updates["wants_to_buy"] = extraction.get("wants_to_buy", False)
    else:
        for need in extract_needs(text):
            if need not in needs:
                needs.append(need)
        budget = extract_budget(text)
        if budget is not None:
            constraints["budget_max"] = budget
        updates["wants_to_buy"] = extract_purchase_intent(text)

    updates["customer_needs"] = needs
    updates["constraints"] = constraints

    if state["funnel_stage"] == FunnelStage.DISCOVERY and (needs or constraints):
        updates["funnel_stage"] = FunnelStage.CONSIDERATION

    return updates


def route_after_discovery(state: ProductPurchaseGraphState) -> str:
    wants_to_buy = state.get("wants_to_buy", False)
    has_a_product_in_mind = bool(state["candidate_products"]) or state["selected_product_id"] is not None

    if wants_to_buy and has_a_product_in_mind:
        return "select_product"

    has_enough_to_search = state["constraints"].get("budget_max") is not None or state.get(
        "budget_unknown", False
    )
    return "product_search" if has_enough_to_search else "ask_for_budget"


def ask_for_budget_node(state: ProductPurchaseGraphState) -> dict:
    if state["customer_needs"]:
        situation = "Ask the customer what budget (in local currency) they have in mind for the purchase."
        fallback = "¿Qué presupuesto tenés?"
    else:
        situation = "Ask the customer what they're looking for and what budget they have in mind."
        fallback = "Contame qué estás buscando y con qué presupuesto contás."

    reply = generate_reply(situation, {"customer_needs": state["customer_needs"]}, fallback)
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
        fallback = (
            "No encontré productos que cumplan esas condiciones. "
            "¿Querés ajustar el presupuesto o contarme más sobre lo que buscás?"
        )
        reply = generate_reply(
            "No products matched the customer's needs/budget. Ask if they want to adjust the "
            "budget or share more about what they need.",
            {"customer_needs": state["customer_needs"], "budget_max": state["constraints"].get("budget_max")},
            fallback,
        )
        return {"reply": reply, "active_node": "RECOMMENDATION"}

    products_by_id = {product.id: product for product in Product.objects.filter(id__in=ids)}
    ordered = [products_by_id[product_id] for product_id in ids if product_id in products_by_id]

    lines = [f"- {product.name} (${product.price}) — {', '.join(product.use_cases)}" for product in ordered]
    fallback = "Encontré estas opciones para vos:\n" + "\n".join(lines)

    facts = {
        "products": [
            {"name": product.name, "price": str(product.price), "use_cases": product.use_cases}
            for product in ordered
        ]
    }
    reply = generate_reply(
        "Present these product options to the customer as recommendations, mentioning name and "
        "price for each.",
        facts,
        fallback,
    )

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
    product_names = [product.name for product in Product.objects.filter(id__in=state["candidate_products"])]
    fallback = f"¿Cuál de estas opciones querés? {', '.join(product_names)}"

    reply = generate_reply(
        "Ask the customer which of these product options they want to buy.",
        {"products": product_names},
        fallback,
    )
    return {"reply": reply}


def checkout_node(state: ProductPurchaseGraphState) -> dict:
    conversation = Conversation.objects.filter(pk=state["conversation_id"]).first()

    try:
        outcome = create_checkout_for_product(
            product_id=state["selected_product_id"],
            conversation=conversation,
        )
    except ProductUnavailable:
        fallback = "Ese producto ya no está disponible. ¿Querés ver otra opción?"
        reply = generate_reply(
            "The selected product is no longer available. Apologize briefly and offer to show alternatives.",
            {},
            fallback,
        )
        return {"reply": reply, "active_node": "CHECKOUT"}
    except InsufficientStock:
        fallback = "Justo se quedó sin stock ese producto. ¿Querés que te muestre otra opción?"
        reply = generate_reply(
            "The selected product just ran out of stock. Apologize briefly and offer alternatives.",
            {},
            fallback,
        )
        return {"reply": reply, "active_node": "CHECKOUT"}

    fallback = (
        f"¡Listo! Creé tu orden #{outcome.order.id} por ${outcome.order.total}. "
        f"Para completar el pago entrá a {outcome.checkout_result.checkout_url}"
    )
    facts = {
        "order_id": outcome.order.id,
        "total": str(outcome.order.total),
        "checkout_url": outcome.checkout_result.checkout_url,
    }
    reply = generate_reply(
        "The order was created successfully. Tell the customer, mention the total, and tell them "
        "to use the checkout_url link to complete the payment.",
        facts,
        fallback,
    )
    return {"reply": reply, "active_node": "CHECKOUT", "checkout_ready": True}


def _instrumented(node_name: str, fn):
    """Wraps a node so LangGraph's execution of it emits node.started/
    completed/failed (workflows/graph/instrumentation.py) — the node
    functions above stay pure and unaware of events."""

    def wrapper(state: ProductPurchaseGraphState) -> dict:
        return instrument(state["conversation_id"], node_name, "PRODUCT_PURCHASE", lambda: fn(state))

    return wrapper


def build_product_purchase_graph():
    graph = StateGraph(ProductPurchaseGraphState)

    graph.add_node("discovery", _instrumented("DISCOVERY", discovery_node))
    graph.add_node("ask_for_budget", _instrumented("ASK_FOR_BUDGET", ask_for_budget_node))
    graph.add_node("product_search", _instrumented("PRODUCT_SEARCH", product_search_node))
    graph.add_node("recommendation", _instrumented("RECOMMENDATION", recommendation_node))
    graph.add_node("select_product", _instrumented("SELECT_PRODUCT", select_product_node))
    graph.add_node("ask_which_product", _instrumented("ASK_WHICH_PRODUCT", ask_which_product_node))
    graph.add_node("checkout", _instrumented("CHECKOUT", checkout_node))

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

    graph_input: ProductPurchaseGraphState = {
        **state,
        "incoming_message": message_text,
        "reply": "",
        "budget_unknown": False,
    }
    result = _PRODUCT_PURCHASE_GRAPH.invoke(graph_input)

    new_state: SalesState = {field: result[field] for field in SALES_STATE_FIELDS}
    reply = result.get("reply", "")

    return new_state, reply
