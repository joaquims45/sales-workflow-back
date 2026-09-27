"""Discovery extraction provider (ARCHITECTURE.md §13 DiscoveryAgent / §36).

Understands a customer's message beyond the fixed keyword lists in
workflows/graph/extraction.py — needs described in free language ("una
placa de video mejor") and an explicit "I don't know my budget" both fall
outside what keyword matching can catch, and previously left DISCOVERY
repeating the same clarifying question forever.

Only extracts structured facts (needs, budget) — it never writes the reply
text itself, and it never invents product/pricing data (ARCHITECTURE.md
§52). Falls back to None when no OPENAI_API_KEY is configured, in which
case the DISCOVERY node uses its own deterministic keyword extraction
instead — same resolver pattern as PaymentProvider/Jev/routing escalation.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    from workflows.graph.state import SalesState

logger = logging.getLogger(__name__)


class DiscoveryExtraction(TypedDict):
    needs: list[str]
    budget_max: int | None
    budget_unknown: bool
    wants_to_buy: bool


class DiscoveryExtractionProvider(Protocol):
    def extract(self, message_text: str, state: "SalesState") -> DiscoveryExtraction | None:
        """Returns extracted facts, or None if extraction isn't available."""
        ...


class NullDiscoveryExtractionProvider:
    def extract(self, message_text: str, state: "SalesState") -> DiscoveryExtraction | None:
        return None


_PROMPT_TEMPLATE = """You are extracting structured facts from a customer's message in a sales \
conversation about buying a tech product. The catalog only has these categories: notebooks, \
monitors, keyboards, mice, headphones — there is no standalone "graphics card" product, so wanting \
better graphics/gaming performance should be captured as a need like "gaming", not invented as its \
own category.

Respond with only a JSON object:
{{"needs": [<short lowercase tags for what they want/need, e.g. "gaming", "programming", "office">], \
"budget_max": <integer budget in local currency mentioned in THIS message, or null if none>, \
"budget_unknown": <true only if they explicitly said they don't know or have no budget in mind>, \
"wants_to_buy": <true if this message expresses they want to go ahead with one of the candidate \
products below — e.g. "me interesa la lenovo", "si, esa", "dale, la llevo" — false otherwise. Only \
true when candidate products were already offered.>}}

primary_goal so far: {primary_goal}
needs already known: {existing_needs}
budget already known: {existing_budget}
candidate products already offered: {candidate_products}
new message: {message!r}"""


class OpenAIDiscoveryExtractionProvider:
    def __init__(self, model: str | None = None, client=None):
        from django.conf import settings

        self._model = model or settings.OPENAI_LLM_MODEL

        if client is not None:
            self._client = client
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def extract(self, message_text: str, state: "SalesState") -> DiscoveryExtraction | None:
        from apps.catalog.models import Product

        candidate_ids = state.get("candidate_products") or []
        candidate_names = list(Product.objects.filter(id__in=candidate_ids).values_list("name", flat=True))

        prompt = _PROMPT_TEMPLATE.format(
            primary_goal=state.get("primary_goal"),
            existing_needs=state.get("customer_needs") or [],
            existing_budget=(state.get("constraints") or {}).get("budget_max"),
            candidate_products=candidate_names,
            message=message_text,
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
        except Exception:
            logger.warning("OpenAI discovery extraction failed.", exc_info=True)
            return None

        needs = data.get("needs")
        if not isinstance(needs, list) or not all(isinstance(need, str) for need in needs):
            needs = []

        budget_max = data.get("budget_max")
        budget_max = int(budget_max) if isinstance(budget_max, (int, float)) else None

        return {
            "needs": needs,
            "budget_max": budget_max,
            "budget_unknown": bool(data.get("budget_unknown", False)),
            "wants_to_buy": bool(data.get("wants_to_buy", False)),
        }


def get_discovery_extraction_provider() -> DiscoveryExtractionProvider:
    from django.conf import settings

    if not settings.OPENAI_API_KEY:
        return NullDiscoveryExtractionProvider()

    try:
        return OpenAIDiscoveryExtractionProvider()
    except Exception:
        logger.warning(
            "Could not initialize OpenAIDiscoveryExtractionProvider, falling back to null.", exc_info=True
        )
        return NullDiscoveryExtractionProvider()
