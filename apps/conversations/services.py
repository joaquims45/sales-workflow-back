import logging
import time

from events.bus import emit_event
from workflows.graph.orchestrator import run_chitchat, run_replace, run_side_query
from workflows.graph.product_purchase import run_product_purchase
from workflows.graph.state import RoutingDecision, SalesState, build_initial_state
from workflows.routing.router import route_message

from .models import Conversation, SalesStateSnapshot

logger = logging.getLogger(__name__)


def get_or_create_state(conversation: Conversation) -> SalesState:
    snapshot, _created = SalesStateSnapshot.objects.get_or_create(
        conversation=conversation,
        defaults={"state": build_initial_state(conversation.id)},
    )
    return snapshot.state


def _run_side_query_turn(conversation: Conversation, state: SalesState, message_text: str) -> tuple[SalesState, str]:
    emit_event(
        conversation,
        "workflow.suspended",
        {"workflow": state["active_workflow"], "node": state["active_node"]},
    )

    new_state, reply = run_side_query(state, message_text)

    if new_state["interruption"] is None:
        # Resolved this turn — actually resumed the suspended workflow.
        emit_event(
            conversation,
            "workflow.resumed",
            {"workflow": new_state["active_workflow"], "node": new_state["active_node"]},
        )
    # else: still waiting on a usable answer (e.g. no destination yet) —
    # stays suspended, next message comes straight back here.

    return new_state, reply


def advance_conversation(conversation: Conversation, message_text: str) -> tuple[SalesState, str]:
    """Run one turn of the sales workflow, persist the resulting state, and
    emit the WorkflowEvents that turn produced (ARCHITECTURE.md §20/§21)."""

    turn_started_at = time.perf_counter()
    emit_event(conversation, "message.received", {"content": message_text})

    state = get_or_create_state(conversation)
    was_active_before = state["active_workflow"] is not None

    if state["interruption"] == "SHIPPING_QUERY":
        # A previous turn already asked a direct follow-up (e.g. "which
        # destination?") and got no usable answer. This message answers
        # it — there's nothing to classify, so skip the router entirely
        # rather than let it misroute a bare place name or number.
        new_state, reply = _run_side_query_turn(conversation, state, message_text)
    else:
        state, raw_decision, decide_latency_ms = route_message(state, message_text)
        emit_event(conversation, "jev.decision", {**raw_decision, "latency_ms": round(decide_latency_ms, 2)})
        emit_event(
            conversation,
            "routing.completed",
            {"decision": state["routing_decision"], "confidence": state["routing_confidence"]},
        )

        if state["routing_decision"] == RoutingDecision.CHITCHAT and state["primary_goal"] is None:
            # A greeting is the conversation starting, not an aside to
            # brush off — never CHITCHAT before a goal even exists,
            # regardless of what the model/heuristic decided.
            logger.info("Downgrading CHITCHAT to CONTINUE: no primary_goal yet.")
            state["routing_decision"] = RoutingDecision.CONTINUE

        if state["routing_decision"] == RoutingDecision.SIDE_QUERY:
            new_state, reply = _run_side_query_turn(conversation, state, message_text)
        elif state["routing_decision"] == RoutingDecision.CHITCHAT:
            new_state, reply = run_chitchat(state, message_text)
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

    turn_latency_ms = (time.perf_counter() - turn_started_at) * 1000
    emit_event(conversation, "message.processed", {"latency_ms": round(turn_latency_ms, 2)})

    return new_state, reply
