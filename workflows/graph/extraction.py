"""Small, deterministic text extraction helpers used by DISCOVERY.

These are intentionally simple keyword/regex rules, not an LLM call. They
exist to get a working DISCOVERY node before Jev/LLM reasoning is
introduced (M6+). Replacing this with real NLU is expected later — the
node contract (text in, structured fields out) is what matters.
"""

from __future__ import annotations

import re

BUDGET_PATTERN = re.compile(r"\$?\s*([\d]{1,3}(?:[.,]\d{3})+|\d{4,})")

NEED_KEYWORDS = {
    "gaming": ["gamer", "jugar", "juegos"],
    "programming": ["programar", "programaci", "codear", "docker"],
    "office": ["oficina", "trabajo", "documentos"],
}


def extract_needs(text: str) -> list[str]:
    lowered = text.lower()
    return [need for need, keywords in NEED_KEYWORDS.items() if any(k in lowered for k in keywords)]


def extract_budget(text: str) -> int | None:
    match = BUDGET_PATTERN.search(text)
    if not match:
        return None
    raw_value = match.group(1).replace(".", "").replace(",", "")
    return int(raw_value)
