"""Embedding provider abstraction (see ARCHITECTURE.md §36).

The default implementation is a deterministic hashing embedding: no model
download, no API key, no network call — so the project runs fully offline
out of the box. It is intentionally simple (a bag-of-words hashed into a
fixed-size vector); swapping it for a real embedding model later only means
implementing `EmbeddingProvider` and changing `get_embedding_provider()`.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

_TOKEN_PATTERN = re.compile(r"[a-záéíóúñ0-9]+")


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbeddingProvider:
    """Deterministic, dependency-free bag-of-words hashing embedding."""

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype="float32")

        for row, text in enumerate(texts):
            for token in _TOKEN_PATTERN.findall(text.lower()):
                bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimension
                vectors[row, bucket] += 1.0

            norm = np.linalg.norm(vectors[row])
            if norm > 0:
                vectors[row] /= norm

        return vectors


def get_embedding_provider() -> EmbeddingProvider:
    return HashingEmbeddingProvider()
