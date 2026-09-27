"""LLM provider abstraction, scoped to routing escalation for now
(ARCHITECTURE.md §36).

This is deliberately narrow — one method, not a general chat/completions
interface — because routing escalation is the only place a frontier LLM is
invoked so far. A broader AIProvider can grow out of this once agents need
open-ended generation (see MVP agents in ARCHITECTURE.md §13).

`get_routing_llm_provider()` switches to a real OpenAI-backed provider once
OPENAI_API_KEY is configured — same resolver pattern as PaymentProvider/Jev.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from workflows.graph.state import SalesState
    from workflows.routing.decision_model import RoutingResult

logger = logging.getLogger(__name__)

_VALID_DECISIONS = {"CONTINUE", "SIDE_QUERY", "REPLACE", "CHITCHAT"}

# What each active_node is actually asking for — without this, a bare
# number or place name looks ambiguous to the model. With it, it's an
# obvious direct answer. Mirrors workflows/routing/jev_router.py.
_NODE_EXPECTATIONS = {
    None: "The conversation just started; nothing has been asked yet.",
    "DISCOVERY": 'Gathering what the customer wants and their budget. A short answer (a '
    'product type, a number, "no sé", etc.) is almost always answering that.',
    "PRODUCT_SEARCH": "Looking up matching products — no question pending.",
    "RECOMMENDATION": "Just showed product options; a short reply likely reacts to them.",
    "CHECKOUT": "Finalizing the purchase.",
    "EXTRACT_DESTINATION": "Just asked which city/town to quote shipping for. A bare place "
    'name ("Chivilcoy", "Santa Fe") is that answer, not a new topic.',
}

_PROMPT_TEMPLATE = """You are the router for a conversational sales workflow, called only when \
Jev's own classification was too uncertain to trust. Given the customer's new message and the \
conversation's current state, decide how to route it.

Respond with only a JSON object: \
{{"decision": "CONTINUE"|"SIDE_QUERY"|"REPLACE"|"CHITCHAT", "confidence": <0..1>}}.

Default to CONTINUE. Short or ambiguous messages (a number, a place name, "no sé", a one-word \
answer) are CONTINUE unless the message clearly, explicitly signals otherwise — never guess \
SIDE_QUERY/REPLACE just because a message is brief or doesn't obviously relate to the active goal.

- CONTINUE: the message answers or moves forward whatever active_node is currently asking (see \
what_active_node_is_asking below). Also correct when there is no active workflow yet (e.g. a \
greeting that starts the conversation).
- SIDE_QUERY: the message explicitly asks about a different, recognizable topic (shipping, \
warranty, store hours, etc.) than what's being asked, without abandoning the current goal.
- REPLACE: the message explicitly abandons the current goal and states a different one \
(e.g. "olvidate de eso, mejor quiero..."). Never for a plain answer to the current question.
- CHITCHAT: the message is a greeting, thanks, acknowledgment, or farewell that doesn't answer \
active_node's question and doesn't raise a new topic — purely conversational filler. ONLY valid \
when primary_goal is not null; if primary_goal is null, a greeting is the conversation starting \
and must be CONTINUE, never CHITCHAT.

Examples:
- active_node=null, message="hola" -> CONTINUE (just a greeting, nothing to interrupt or replace)
- active_node="EXTRACT_DESTINATION", message="Chivilcoy" -> CONTINUE (answering the destination \
question)
- active_node="DISCOVERY", message="2 millones" -> CONTINUE (answering the budget question)
- active_node="RECOMMENDATION", message="¿Hacen envíos a Santa Fe?" -> SIDE_QUERY (explicit, \
recognizable shipping question)
- active_node="RECOMMENDATION", message="olvidate, mejor quiero un monitor" -> REPLACE (explicit \
goal change)
- primary_goal="BUY_PRODUCT", active_node="CHECKOUT", message="genial muchas gracias" -> CHITCHAT \
(thanks after checkout is already in progress/complete, not answering or changing anything)
- primary_goal="BUY_PRODUCT", active_node="RECOMMENDATION", message="hola" -> CHITCHAT (a stray \
greeting mid-goal, not a new topic and not answering the recommendation)

primary_goal: {primary_goal}
active_workflow: {active_workflow}
active_node: {active_node}
what_active_node_is_asking: {node_expectation}
message: {message!r}"""


class RoutingLLMProvider(Protocol):
    def decide_routing(self, message_text: str, state: "SalesState") -> "RoutingResult | None":
        """Returns a routing decision, or None if escalation isn't available."""
        ...


class NullRoutingLLMProvider:
    """Default provider: no LLM is configured.

    Returns None (cannot escalate) rather than fabricating a decision, so
    the router falls back to Jev's own low-confidence call. This keeps the
    project runnable with zero external LLM credentials by default.
    """

    def decide_routing(self, message_text: str, state: "SalesState") -> "RoutingResult | None":
        return None


class OpenAIRoutingLLMProvider:
    """Escalates ambiguous routing decisions to an OpenAI chat model."""

    def __init__(self, model: str | None = None, client=None):
        from django.conf import settings

        self._model = model or settings.OPENAI_LLM_MODEL

        if client is not None:
            self._client = client
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def decide_routing(self, message_text: str, state: "SalesState") -> "RoutingResult | None":
        active_node = state.get("active_node")
        prompt = _PROMPT_TEMPLATE.format(
            primary_goal=state.get("primary_goal"),
            active_workflow=state.get("active_workflow"),
            active_node=active_node,
            node_expectation=_NODE_EXPECTATIONS.get(active_node, "Continuing the active workflow."),
            message=message_text,
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
            decision = data.get("decision")
            confidence = float(data.get("confidence", 0.9))
        except Exception:
            logger.warning("OpenAI routing escalation failed.", exc_info=True)
            return None

        if decision not in _VALID_DECISIONS:
            logger.warning("OpenAI routing escalation returned an unknown decision: %r", decision)
            return None

        return {"decision": decision, "confidence": confidence}


def get_routing_llm_provider() -> RoutingLLMProvider:
    from django.conf import settings

    if not settings.OPENAI_API_KEY:
        return NullRoutingLLMProvider()

    try:
        return OpenAIRoutingLLMProvider()
    except Exception:
        logger.warning("Could not initialize OpenAIRoutingLLMProvider, falling back to null.", exc_info=True)
        return NullRoutingLLMProvider()
