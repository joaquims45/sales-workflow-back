from events.bus import emit_event
from workflows.graph.orchestrator import run_replace, run_side_query
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
    """Run one turn of the sales workflow, persist the resulting state, and
    emit the WorkflowEvents that turn produced (ARCHITECTURE.md §20)."""

    state = get_or_create_state(conversation)
    was_active_before = state["active_workflow"] is not None

    state, raw_decision = route_message(state, message_text)
    emit_event(conversation, "jev.decision", raw_decision)
    emit_event(
        conversation,
        "routing.completed",
        {"decision": state["routing_decision"], "confidence": state["routing_confidence"]},
    )

    if state["routing_decision"] == RoutingDecision.SIDE_QUERY:
        emit_event(
            conversation,
            "workflow.suspended",
            {"workflow": state["active_workflow"], "node": state["active_node"]},
        )
        # Suspends the active workflow, answers via SHIPPING_QUERY, resumes.
        new_state, reply = run_side_query(state, message_text)
        emit_event(
            conversation,
            "workflow.resumed",
            {"workflow": new_state["active_workflow"], "node": new_state["active_node"]},
        )
    elif state["routing_decision"] == RoutingDecision.REPLACE:
        emit_event(
            conversation,
            "workflow.replaced",
            {"previous_workflow": state["active_workflow"], "previous_node": state["active_node"]},
        )
        # Closes the current goal and starts a fresh PRODUCT_PURCHASE.
        new_state, reply = run_replace(state, message_text)
        if new_state["active_workflow"] is not None:
            emit_event(conversation, "workflow.started", {"workflow": new_state["active_workflow"]})
    else:
        new_state, reply = run_product_purchase(state, message_text)
        if not was_active_before and new_state["active_workflow"] is not None:
            emit_event(conversation, "workflow.started", {"workflow": new_state["active_workflow"]})

    SalesStateSnapshot.objects.filter(conversation=conversation).update(state=new_state)
    return new_state, reply
