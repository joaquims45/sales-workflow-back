"""Node-level instrumentation (ARCHITECTURE.md §20/§21).

Wraps a graph node so its execution emits `node.started` before and
`node.completed`/`node.failed` after, via the EventBus — without the node's
own function knowing anything about events. Registered at build-graph time
(see `build_product_purchase_graph`), not inside each node's own logic.

Best-effort: if the conversation can't be found (shouldn't happen in
practice — it exists before any graph runs), instrumentation is silently
skipped rather than breaking the turn.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from apps.conversations.models import Conversation
from events.bus import emit_event

T = TypeVar("T")


def instrument(conversation_id: int, node_name: str, workflow: str, fn: Callable[[], T]) -> T:
    """Runs fn(), emitting node.started before and node.completed/failed
    after. Re-raises whatever fn() raises, after emitting node.failed."""

    conversation = Conversation.objects.filter(pk=conversation_id).first()

    if conversation is not None:
        emit_event(conversation, "node.started", {"node": node_name, "workflow": workflow})

    started_at = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        if conversation is not None:
            duration_ms = (time.perf_counter() - started_at) * 1000
            emit_event(
                conversation,
                "node.failed",
                {
                    "node": node_name,
                    "workflow": workflow,
                    "error": str(exc),
                    "duration_ms": round(duration_ms, 2),
                },
            )
        raise

    if conversation is not None:
        duration_ms = (time.perf_counter() - started_at) * 1000
        emit_event(
            conversation,
            "node.completed",
            {"node": node_name, "workflow": workflow, "duration_ms": round(duration_ms, 2)},
        )

    return result
