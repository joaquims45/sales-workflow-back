import numpy as np
from django.test import SimpleTestCase

from workflows.graph.state import build_initial_state

from .embeddings import HashingEmbeddingProvider
from .llm import NullRoutingLLMProvider, get_routing_llm_provider


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


class NullRoutingLLMProviderTests(SimpleTestCase):
    def test_returns_none_signaling_no_escalation(self):
        provider = NullRoutingLLMProvider()
        state = build_initial_state(conversation_id=1)

        result = provider.decide_routing("¿Hacen envíos a Santa Fe?", state)

        self.assertIsNone(result)


class GetRoutingLLMProviderTests(SimpleTestCase):
    def test_returns_null_provider_by_default(self):
        self.assertIsInstance(get_routing_llm_provider(), NullRoutingLLMProvider)
