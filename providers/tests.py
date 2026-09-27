import numpy as np
from django.test import SimpleTestCase

from .embeddings import HashingEmbeddingProvider


class HashingEmbeddingProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = HashingEmbeddingProvider(dimension=64)

    def test_embed_returns_expected_shape(self):
        vectors = self.provider.embed(["notebook gamer", "monitor 27 pulgadas"])

        self.assertEqual(vectors.shape, (2, 64))

    def test_embed_is_deterministic(self):
        first = self.provider.embed(["notebook para programar"])
        second = self.provider.embed(["notebook para programar"])

        np.testing.assert_array_equal(first, second)

    def test_embed_normalizes_vectors(self):
        vectors = self.provider.embed(["gaming programming docker"])

        norm = np.linalg.norm(vectors[0])
        self.assertAlmostEqual(norm, 1.0, places=5)
