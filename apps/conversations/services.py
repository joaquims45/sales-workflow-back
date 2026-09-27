from workflows.graph.product_purchase import run_product_purchase
from workflows.graph.state import SalesState, build_initial_state

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
    new_state, reply = run_product_purchase(state, message_text)

    SalesStateSnapshot.objects.filter(conversation=conversation).update(state=new_state)
    return new_state, reply
