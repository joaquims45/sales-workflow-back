"""Embedding provider abstraction (see ARCHITECTURE.md §36).

The default implementation is a deterministic hashing embedding: no model
download, no API key, no network call — so the project runs fully offline
out of the box. `get_embedding_provider()` switches to OpenAI's real
embedding model once OPENAI_API_KEY is configured — same resolver pattern
as PaymentProvider/Jev (a working, credential-free default; a real
provider behind config).

Both providers L2-normalize their output, since rag/indexer.py and
rag/retriever.py use FAISS's inner product as cosine similarity — that only
holds for unit vectors.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)

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


class OpenAIEmbeddingProvider:
    """Real semantic embeddings via OpenAI. Requires OPENAI_API_KEY."""

    def __init__(self, model: str | None = None, dimension: int | None = None, client=None):
        from django.conf import settings

        self._model = model or settings.OPENAI_EMBEDDING_MODEL
        self.dimension = dimension or settings.OPENAI_EMBEDDING_DIMENSIONS

        if client is not None:
            self._client = client
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def embed(self, texts: list[str]) -> np.ndarray:
        response = self._client.embeddings.create(
            model=self._model, input=texts, dimensions=self.dimension
        )
        vectors = np.array([item.embedding for item in response.data], dtype="float32")

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return vectors / norms


def get_embedding_provider() -> EmbeddingProvider:
    from django.conf import settings

    if not settings.OPENAI_API_KEY:
        return HashingEmbeddingProvider()

    try:
        return OpenAIEmbeddingProvider()
    except Exception:
        logger.warning("Could not initialize OpenAIEmbeddingProvider, falling back to hashing.", exc_info=True)
        return HashingEmbeddingProvider()
