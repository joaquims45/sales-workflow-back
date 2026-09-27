"""Structured conversational state for Sales Workflow.

This module defines SalesState as a plain, typed, JSON-serializable
structure. It intentionally does not depend on LangGraph yet (that lands in
M4+): the goal here is to validate the shape of the state and how it
persists, independently of any orchestration engine.
"""

from __future__ import annotations

from typing import Any, TypedDict


class WorkflowFrame(TypedDict):
    """A single entry in the workflow_stack (see ARCHITECTURE.md §14)."""

    workflow: str
    node: str


class SalesState(TypedDict):
    conversation_id: int

    primary_goal: str | None
    intent: str | None

    customer_needs: list[str]
    constraints: dict[str, Any]

    candidate_products: list[int]
    selected_product_id: int | None

    funnel_stage: str

    active_workflow: str | None
    active_node: str | None

    suspended_workflow: str | None
    suspended_node: str | None
    workflow_stack: list[WorkflowFrame]

    interruption: str | None

    routing_decision: str | None
    routing_confidence: float | None

    checkout_ready: bool


class FunnelStage:
    DISCOVERY = "DISCOVERY"
    CONSIDERATION = "CONSIDERATION"
    DECISION = "DECISION"


class PrimaryGoal:
    BUY_PRODUCT = "BUY_PRODUCT"


class RoutingDecision:
    CONTINUE = "CONTINUE"
    SIDE_QUERY = "SIDE_QUERY"
    REPLACE = "REPLACE"
    CHITCHAT = "CHITCHAT"
    RESUME = "RESUME"


def build_initial_state(conversation_id: int) -> SalesState:
    """The state every new conversation starts from."""

    return SalesState(
        conversation_id=conversation_id,
        primary_goal=None,
        intent=None,
        customer_needs=[],
        constraints={},
        candidate_products=[],
        selected_product_id=None,
        funnel_stage=FunnelStage.DISCOVERY,
        active_workflow=None,
        active_node=None,
        suspended_workflow=None,
        suspended_node=None,
        workflow_stack=[],
        interruption=None,
        routing_decision=None,
        routing_confidence=None,
        checkout_ready=False,
    )
