"""Natural-language reply generation (ARCHITECTURE.md §13/§36/§52).

Turns a node's already-decided outcome into conversational text. The LLM
only phrases what happened — it never decides prices, stock, or which
products exist. A node computes `facts` from Postgres/tool results first;
the model is instructed to use them verbatim and invent nothing else. This
is what keeps a graph node's replies from sounding like a form ("¿Qué
presupuesto tenés?" every time) without giving the LLM any say over
commercial data (ARCHITECTURE.md §52: AI is never the source of truth for
prices/stock/orders).

Falls back to the caller's own template string when no OPENAI_API_KEY is
configured or the call fails — same resolver pattern as every other
provider in this project. `generate_reply()` is the one function graph
nodes call; they never touch the provider directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a friendly sales assistant chatting in Spanish (Argentina, informal \
"vos"). You're given a situation and a set of facts already decided by the store's systems. Write \
a short, natural reply for the customer.

Rules:
- Use ONLY the facts given. Never invent a product, price, stock figure, or shipping detail that \
isn't listed there.
- Keep it conversational — this is a chat, not a form. 1-3 sentences; when listing named options, \
a short list is fine.
- Reply in plain text only — no JSON, no markdown headers."""


class ReplyGenerationProvider(Protocol):
    def generate(self, situation: str, facts: dict[str, Any]) -> str | None:
        """Returns a natural-language reply, or None if unavailable."""
        ...


class NullReplyGenerationProvider:
    def generate(self, situation: str, facts: dict[str, Any]) -> str | None:
        return None


class OpenAIReplyGenerationProvider:
    def __init__(self, model: str | None = None, client=None):
        from django.conf import settings

        self._model = model or settings.OPENAI_LLM_MODEL

        if client is not None:
            self._client = client
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate(self, situation: str, facts: dict[str, Any]) -> str | None:
        prompt = f"Situation: {situation}\n\nFacts (JSON — the only source of truth): " + json.dumps(
            facts, ensure_ascii=False
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content
        except Exception:
            logger.warning("OpenAI reply generation failed.", exc_info=True)
            return None

        return text.strip() if text else None


def get_reply_generation_provider() -> ReplyGenerationProvider:
    from django.conf import settings

    if not settings.OPENAI_API_KEY:
        return NullReplyGenerationProvider()

    try:
        return OpenAIReplyGenerationProvider()
    except Exception:
        logger.warning(
            "Could not initialize OpenAIReplyGenerationProvider, falling back to null.", exc_info=True
        )
        return NullReplyGenerationProvider()


def generate_reply(situation: str, facts: dict[str, Any], fallback: str) -> str:
    """What every graph node calls: LLM phrasing when available, the
    node's own deterministic template string otherwise."""

    generated = get_reply_generation_provider().generate(situation, facts)
    return generated if generated else fallback
