"""Tools that agents/graph nodes use to touch the product domain.

These are the only sanctioned way to read commercial data (price, stock,
availability) from Sales Workflow nodes — never the ORM directly from a
node, and never invented by an LLM. See ARCHITECTURE.md §16.

`search_products` uses the FAISS semantic index (rag/retriever.py) to rank
candidates when it exists, then always re-reads price/stock from PostgreSQL.
If no index has been built yet, it falls back to a naive keyword-overlap
filter so the tool still works on a fresh checkout (before `reindex_products`
has ever run).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.catalog.models import Product
from rag.retriever import semantic_search


@dataclass
class ProductConstraints:
    budget_max: int | None = None
    needs: list[str] = field(default_factory=list)


@dataclass
class ProductCandidate:
    id: int
    name: str
    price: str
    features: dict
    use_cases: list[str]


def search_products(query: str, constraints: ProductConstraints, limit: int = 5) -> list[ProductCandidate]:
    semantic_ids = semantic_search(query, top_k=max(limit * 4, 20))

    queryset = Product.objects.filter(is_active=True)
    if constraints.budget_max is not None:
        queryset = queryset.filter(price__lte=constraints.budget_max)
    if semantic_ids is not None:
        queryset = queryset.filter(id__in=semantic_ids)

    candidates = []
    for product in queryset:
        # Without a semantic index we still need some way to discard
        # irrelevant matches, so fall back to a plain keyword overlap.
        if semantic_ids is None and constraints.needs and not set(constraints.needs) & set(product.use_cases):
            continue
        candidates.append(
            ProductCandidate(
                id=product.id,
                name=product.name,
                price=str(product.price),
                features=product.features,
                use_cases=product.use_cases,
            )
        )

    def rank(candidate: ProductCandidate) -> tuple[int, int, float]:
        semantic_rank = semantic_ids.index(candidate.id) if semantic_ids is not None else 0
        matched_needs = len(set(constraints.needs) & set(candidate.use_cases)) if constraints.needs else 0
        return (semantic_rank, -matched_needs, float(candidate.price))

    candidates.sort(key=rank)
    return candidates[:limit]
