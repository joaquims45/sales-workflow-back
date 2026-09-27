"""Builds the FAISS semantic index over the product catalog.

FAISS is only a semantic index (ARCHITECTURE.md §15): it stores nothing
about price/stock/availability, only an embedding per product id. Commercial
data always comes back from PostgreSQL at query time.
"""

from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np
from django.conf import settings

from apps.catalog.models import Product
from providers.embeddings import get_embedding_provider


def build_product_text(product: Product) -> str:
    parts = [product.name, product.description, product.category.name]
    parts += [str(value) for value in product.features.values()]
    parts += product.use_cases
    parts += product.semantic_tags
    return " ".join(str(part) for part in parts)


def build_index() -> int:
    """(Re)builds the FAISS index from active products and persists it to disk.

    Returns the number of products indexed.
    """

    provider = get_embedding_provider()
    products = list(Product.objects.filter(is_active=True).select_related("category"))

    index_path = Path(settings.FAISS_INDEX_PATH)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    index = faiss.IndexIDMap2(faiss.IndexFlatIP(provider.dimension))

    if products:
        texts = [build_product_text(product) for product in products]
        vectors = provider.embed(texts)
        ids = np.array([product.id for product in products], dtype="int64")
        index.add_with_ids(vectors, ids)

    faiss.write_index(index, str(index_path))
    return len(products)
