from workflows.graph.state import SalesState, build_initial_state
from workflows.graph.transitions import apply_hardcoded_transition

from .models import Conversation, SalesStateSnapshot


def get_or_create_state(conversation: Conversation) -> SalesState:
    snapshot, _created = SalesStateSnapshot.objects.get_or_create(
        conversation=conversation,
        defaults={"state": build_initial_state(conversation.id)},
    )
    return snapshot.state


def update_state_from_message(conversation: Conversation, message_text: str) -> SalesState:
    state = get_or_create_state(conversation)
    state = apply_hardcoded_transition(state, message_text)

    SalesStateSnapshot.objects.filter(conversation=conversation).update(state=state)
    return state
