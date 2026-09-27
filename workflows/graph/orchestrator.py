"""Acts on SIDE_QUERY (suspend/resume), REPLACE (close/restart goal), and
CHITCHAT (conversational aside, no state change) decisions from the router
(ARCHITECTURE.md §8-10).

Only SHIPPING_QUERY exists today, so run_side_query dispatches to it
directly — a real dispatcher (picking among multiple side workflows from
the message) only earns its place once a second one (e.g. WARRANTY_QUERY)
exists.

RESUME is not something the router decides (ARCHITECTURE.md §6): it's the
internal transition run_side_query performs once the side workflow
completes, restoring active_workflow/active_node from workflow_stack.
"""

from __future__ import annotations

import logging
import time

from apps.conversations.models import Conversation
from events.bus import emit_event
from providers.reply import generate_reply

from .instrumentation import instrument
from .product_purchase import run_product_purchase
from .shipping_query import run_shipping_query
from .state import RoutingDecision, SalesState, build_initial_state

logger = logging.getLogger(__name__)


def run_side_query(state: SalesState, message_text: str) -> tuple[SalesState, str]:
    # From the main graph's point of view, SHIPPING_QUERY is one node —
    # node.started fires once (when it's first entered), node.completed
    # only once it actually resolves (may span more than one turn if it
    # had to ask for a destination first).
    conversation = Conversation.objects.filter(pk=state["conversation_id"]).first()

    # If we're already mid a SHIPPING_QUERY (it asked for a destination and
    # got none last turn), this message answers that — don't push another
    # frame onto the stack, just re-run shipping with the new message.
    already_pending = state["interruption"] == "SHIPPING_QUERY"

    if not already_pending:
        previous_workflow = state["active_workflow"]
        previous_node = state["active_node"]

        if previous_workflow is not None:
            state["workflow_stack"] = state["workflow_stack"] + [
                {"workflow": previous_workflow, "node": previous_node}
            ]
        state["suspended_workflow"] = previous_workflow
        state["suspended_node"] = previous_node
        state["interruption"] = "SHIPPING_QUERY"
        state["active_workflow"] = "SHIPPING_QUERY"
        state["active_node"] = "EXTRACT_DESTINATION"

        if conversation is not None:
            emit_event(conversation, "node.started", {"node": "SHIPPING_QUERY", "workflow": "SHIPPING_QUERY"})

    started_at = time.perf_counter()
    reply, resolved = run_shipping_query(message_text)
    duration_ms = (time.perf_counter() - started_at) * 1000

    if not resolved:
        # Still no usable destination — stay suspended so the next message
        # comes straight back here instead of being routed from scratch.
        # No node.completed yet: it's still running, just waiting on the
        # customer's next message.
        state["routing_decision"] = RoutingDecision.SIDE_QUERY
        state["routing_confidence"] = 1.0
        return state, reply

    if conversation is not None:
        emit_event(
            conversation,
            "node.completed",
            {"node": "SHIPPING_QUERY", "workflow": "SHIPPING_QUERY", "duration_ms": round(duration_ms, 2)},
        )

    if state["workflow_stack"]:
        frame = state["workflow_stack"][-1]
        state["workflow_stack"] = state["workflow_stack"][:-1]
        state["active_workflow"] = frame["workflow"]
        state["active_node"] = frame["node"]
    else:
        state["active_workflow"] = None
        state["active_node"] = None

    state["suspended_workflow"] = None
    state["suspended_node"] = None
    state["interruption"] = None
    state["routing_decision"] = RoutingDecision.RESUME
    state["routing_confidence"] = 1.0

    return state, reply


def run_replace(state: SalesState, message_text: str) -> tuple[SalesState, str]:
    """Closes the current goal and starts a fresh PRODUCT_PURCHASE from this message.

    Full history/traceability of the replaced workflow is a tracing concern
    (M10) — for now this only logs it, matching how Jev fallbacks are
    logged elsewhere in workflows/routing.
    """

    if state["active_workflow"] is not None:
        logger.info(
            "Replacing workflow %s (node %s) with a new goal.",
            state["active_workflow"],
            state["active_node"],
        )

    replaced_confidence = state["routing_confidence"]

    fresh_state = build_initial_state(state["conversation_id"])
    fresh_state["routing_decision"] = RoutingDecision.REPLACE
    fresh_state["routing_confidence"] = replaced_confidence

    return run_product_purchase(fresh_state, message_text)


def run_chitchat(state: SalesState, message_text: str) -> tuple[SalesState, str]:
    """Replies to a conversational aside (greeting/thanks/farewell) without
    touching any workflow state — no node re-entry, no side effects. Unlike
    every CONTINUE message, this never re-enters discovery_node, so it can't
    accidentally re-trigger checkout_node after a purchase is already done.

    Guarded by advance_conversation: only reached when primary_goal is
    already set (see RoutingDecision.CHITCHAT's own routing criteria).
    """

    def _generate() -> str:
        return generate_reply(
            situation=(
                "The customer sent a conversational aside (greeting, thanks, or farewell) — "
                "not a question or a new request. Reply briefly and naturally; if a purchase "
                "goal is already in progress or was just completed, you may warmly invite them "
                "to continue."
            ),
            facts={
                "primary_goal": state["primary_goal"],
                "active_node": state["active_node"],
                "checkout_ready": state["checkout_ready"],
            },
            fallback="¡De nada! Cualquier cosa que necesites, decime.",
        )

    reply = instrument(state["conversation_id"], "CHITCHAT", "CHITCHAT", _generate)

    state["routing_decision"] = RoutingDecision.CHITCHAT
    return state, reply
