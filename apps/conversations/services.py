from workflows.graph.orchestrator import run_side_query
from workflows.graph.product_purchase import run_product_purchase
from workflows.graph.state import RoutingDecision, SalesState, build_initial_state
from workflows.routing.router import route_message

from .models import Conversation, SalesStateSnapshot


def get_or_create_state(conversation: Conversation) -> SalesState:
    snapshot, _created = SalesStateSnapshot.objects.get_or_create(
        conversation=conversation,
        defaults={"state": build_initial_state(conversation.id)},
    )
    return snapshot.state


def advance_conversation(conversation: Conversation, message_text: str) -> tuple[SalesState, str]:
    """Run one turn of the sales workflow and persist the resulting state."""

    state = get_or_create_state(conversation)
    state = route_message(state, message_text)

    if state["routing_decision"] == RoutingDecision.SIDE_QUERY:
        # Suspends the active workflow, answers via SHIPPING_QUERY, resumes.
        new_state, reply = run_side_query(state, message_text)
    else:
        # REPLACE isn't implemented yet (M8) — it behaves as CONTINUE for now.
        new_state, reply = run_product_purchase(state, message_text)

    SalesStateSnapshot.objects.filter(conversation=conversation).update(state=new_state)
    return new_state, reply
