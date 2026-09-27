from types import SimpleNamespace
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from workflows.graph.state import build_initial_state

from .embeddings import (
    HashingEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)
from .discovery import (
    NullDiscoveryExtractionProvider,
    OpenAIDiscoveryExtractionProvider,
    get_discovery_extraction_provider,
)
from .llm import (
    NullRoutingLLMProvider,
    OpenAIRoutingLLMProvider,
    get_routing_llm_provider,
)
from .reply import (
    NullReplyGenerationProvider,
    OpenAIReplyGenerationProvider,
    generate_reply,
    get_reply_generation_provider,
)


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

    def test_returns_openai_provider_when_api_key_configured(self):
        with self.settings(OPENAI_API_KEY="test-key-not-real"):
            provider = get_routing_llm_provider()

        self.assertIsInstance(provider, OpenAIRoutingLLMProvider)


class _FakeEmbeddingsClient:
    def __init__(self, vectors):
        self._vectors = vectors
        self.last_call = None
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.last_call = kwargs
        data = [SimpleNamespace(embedding=vector) for vector in self._vectors]
        return SimpleNamespace(data=data)


class OpenAIEmbeddingProviderTests(SimpleTestCase):
    def test_embed_normalizes_vectors_from_the_client(self):
        client = _FakeEmbeddingsClient([[3.0, 4.0]])  # norm 5
        provider = OpenAIEmbeddingProvider(model="text-embedding-3-small", dimension=2, client=client)

        vectors = provider.embed(["notebook gamer"])

        np.testing.assert_allclose(vectors[0], [0.6, 0.8])
        self.assertEqual(client.last_call["model"], "text-embedding-3-small")
        self.assertEqual(client.last_call["dimensions"], 2)


class GetEmbeddingProviderTests(SimpleTestCase):
    def test_returns_hashing_provider_by_default(self):
        with self.settings(OPENAI_API_KEY=""):
            self.assertIsInstance(get_embedding_provider(), HashingEmbeddingProvider)

    def test_returns_openai_provider_when_api_key_configured(self):
        with self.settings(OPENAI_API_KEY="test-key-not-real"):
            provider = get_embedding_provider()

        self.assertIsInstance(provider, OpenAIEmbeddingProvider)


class _FakeChatClient:
    def __init__(self, content):
        self.last_call = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._content = content

    def _create(self, **kwargs):
        self.last_call = kwargs
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class OpenAIRoutingLLMProviderTests(SimpleTestCase):
    def test_parses_a_valid_decision(self):
        client = _FakeChatClient('{"decision": "SIDE_QUERY", "confidence": 0.92}')
        provider = OpenAIRoutingLLMProvider(model="gpt-4o-mini", client=client)
        state = build_initial_state(conversation_id=1)

        result = provider.decide_routing("¿Hacen envíos a Santa Fe?", state)

        self.assertEqual(result, {"decision": "SIDE_QUERY", "confidence": 0.92})
        self.assertEqual(client.last_call["model"], "gpt-4o-mini")

    def test_returns_none_for_malformed_json(self):
        client = _FakeChatClient("not json")
        provider = OpenAIRoutingLLMProvider(client=client)
        state = build_initial_state(conversation_id=1)

        result = provider.decide_routing("mensaje ambiguo", state)

        self.assertIsNone(result)

    def test_returns_none_for_unknown_decision(self):
        client = _FakeChatClient('{"decision": "MAYBE", "confidence": 0.5}')
        provider = OpenAIRoutingLLMProvider(client=client)
        state = build_initial_state(conversation_id=1)

        result = provider.decide_routing("mensaje ambiguo", state)

        self.assertIsNone(result)


class NullDiscoveryExtractionProviderTests(SimpleTestCase):
    def test_returns_none_signaling_no_extraction(self):
        provider = NullDiscoveryExtractionProvider()
        state = build_initial_state(conversation_id=1)

        self.assertIsNone(provider.extract("no sé, busco una placa de video", state))


class GetDiscoveryExtractionProviderTests(SimpleTestCase):
    def test_returns_null_provider_by_default(self):
        self.assertIsInstance(get_discovery_extraction_provider(), NullDiscoveryExtractionProvider)

    def test_returns_openai_provider_when_api_key_configured(self):
        with self.settings(OPENAI_API_KEY="test-key-not-real"):
            provider = get_discovery_extraction_provider()

        self.assertIsInstance(provider, OpenAIDiscoveryExtractionProvider)


class OpenAIDiscoveryExtractionProviderTests(SimpleTestCase):
    def test_parses_needs_and_budget(self):
        client = _FakeChatClient('{"needs": ["gaming"], "budget_max": 1500000, "budget_unknown": false}')
        provider = OpenAIDiscoveryExtractionProvider(client=client)
        state = build_initial_state(conversation_id=1)

        result = provider.extract("Busco algo para jugar, tengo 1.500.000.", state)

        self.assertEqual(result, {"needs": ["gaming"], "budget_max": 1500000, "budget_unknown": False})

    def test_parses_explicit_budget_unknown(self):
        client = _FakeChatClient('{"needs": ["gaming"], "budget_max": null, "budget_unknown": true}')
        provider = OpenAIDiscoveryExtractionProvider(client=client)
        state = build_initial_state(conversation_id=1)

        result = provider.extract("No sé, busco alguna placa de video.", state)

        self.assertEqual(result, {"needs": ["gaming"], "budget_max": None, "budget_unknown": True})

    def test_returns_none_for_malformed_json(self):
        client = _FakeChatClient("not json")
        provider = OpenAIDiscoveryExtractionProvider(client=client)
        state = build_initial_state(conversation_id=1)

        self.assertIsNone(provider.extract("mensaje raro", state))

    def test_ignores_malformed_needs_field(self):
        client = _FakeChatClient('{"needs": "gaming", "budget_max": null, "budget_unknown": false}')
        provider = OpenAIDiscoveryExtractionProvider(client=client)
        state = build_initial_state(conversation_id=1)

        result = provider.extract("mensaje", state)

        self.assertEqual(result["needs"], [])


class NullReplyGenerationProviderTests(SimpleTestCase):
    def test_returns_none_signaling_no_generation(self):
        provider = NullReplyGenerationProvider()

        self.assertIsNone(provider.generate("Ask for a budget.", {}))


class GetReplyGenerationProviderTests(SimpleTestCase):
    def test_returns_null_provider_by_default(self):
        self.assertIsInstance(get_reply_generation_provider(), NullReplyGenerationProvider)

    def test_returns_openai_provider_when_api_key_configured(self):
        with self.settings(OPENAI_API_KEY="test-key-not-real"):
            provider = get_reply_generation_provider()

        self.assertIsInstance(provider, OpenAIReplyGenerationProvider)


class OpenAIReplyGenerationProviderTests(SimpleTestCase):
    def test_returns_the_generated_text(self):
        client = _FakeChatClient("¡Hola! ¿Qué presupuesto tenés en mente?")
        provider = OpenAIReplyGenerationProvider(client=client)

        result = provider.generate("Ask for a budget.", {"customer_needs": ["gaming"]})

        self.assertEqual(result, "¡Hola! ¿Qué presupuesto tenés en mente?")
        self.assertIn("gaming", client.last_call["messages"][1]["content"])

    def test_returns_none_when_the_call_fails(self):
        client = mock.Mock()
        client.chat.completions.create.side_effect = RuntimeError("boom")
        provider = OpenAIReplyGenerationProvider(client=client)

        self.assertIsNone(provider.generate("Ask for a budget.", {}))


class GenerateReplyTests(SimpleTestCase):
    def test_uses_the_fallback_when_no_provider_is_configured(self):
        reply = generate_reply("Ask for a budget.", {}, fallback="¿Qué presupuesto tenés?")

        self.assertEqual(reply, "¿Qué presupuesto tenés?")

    def test_uses_the_generated_text_when_available(self):
        fake_provider = mock.Mock()
        fake_provider.generate.return_value = "Contame tu presupuesto, dale."

        with mock.patch("providers.reply.get_reply_generation_provider", return_value=fake_provider):
            reply = generate_reply("Ask for a budget.", {}, fallback="¿Qué presupuesto tenés?")

        self.assertEqual(reply, "Contame tu presupuesto, dale.")
