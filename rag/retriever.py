"""Semantic retrieval over the FAISS product index.

Returns product ids only — commercial data (price/stock/availability) is
never read from here, only from PostgreSQL (ARCHITECTURE.md §15).
"""

from __future__ import annotations

import logging
from pathlib import Path

import faiss
from django.conf import settings

from providers.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)

_cached_index = None
_cached_key: tuple[str, float] | None = None


def _load_index():
    global _cached_index, _cached_key

    path = Path(settings.FAISS_INDEX_PATH)
    if not path.exists():
        return None

    cache_key = (str(path), path.stat().st_mtime)
    if _cached_key != cache_key:
        _cached_index = faiss.read_index(str(path))
        _cached_key = cache_key

    return _cached_index


def semantic_search(query: str, top_k: int = 20) -> list[int] | None:
    """Returns product ids ranked by semantic similarity to `query`.

    Returns None (instead of an empty list) when no index has been built
    yet, so callers can distinguish "no index" from "no matches" and fall
    back to a non-semantic strategy.
    """

    index = _load_index()
    if index is None or index.ntotal == 0:
        return None

    provider = get_embedding_provider()
    vector = provider.embed([query])

    if vector.shape[1] != index.d:
        # The index was built with a different embedding provider/dimension
        # (e.g. OPENAI_API_KEY was added/changed since the last reindex) —
        # fall back rather than 500ing the whole conversation turn.
        logger.warning(
            "FAISS index dimension (%d) doesn't match the current embedding provider's (%d). "
            "Run manage.py reindex_products. Falling back to the non-semantic search.",
            index.d,
            vector.shape[1],
        )
        return None

    _distances, ids = index.search(vector, min(top_k, index.ntotal))

    return [int(product_id) for product_id in ids[0] if product_id != -1]
