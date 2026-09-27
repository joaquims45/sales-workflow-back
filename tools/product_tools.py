"""Tools that agents/graph nodes use to touch the product domain.

These are the only sanctioned way to read commercial data (price, stock,
availability) from Sales Workflow nodes — never the ORM directly from a
node, and never invented by an LLM. See ARCHITECTURE.md §16.

`search_products` here is a naive Postgres/SQLite filter. It will be
upgraded to a FAISS-backed semantic retrieval in M5, keeping the same
contract (constraints in, ranked candidates out).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.catalog.models import Product


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


def search_products(constraints: ProductConstraints, limit: int = 5) -> list[ProductCandidate]:
    queryset = Product.objects.filter(is_active=True)
    if constraints.budget_max is not None:
        queryset = queryset.filter(price__lte=constraints.budget_max)

    candidates = []
    for product in queryset:
        if constraints.needs and not set(constraints.needs) & set(product.use_cases):
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

    def rank(candidate: ProductCandidate) -> tuple[int, float]:
        matched_needs = len(set(constraints.needs) & set(candidate.use_cases)) if constraints.needs else 0
        return (-matched_needs, float(candidate.price))

    candidates.sort(key=rank)
    return candidates[:limit]
