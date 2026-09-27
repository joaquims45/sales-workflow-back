from unittest import mock

from django.test import SimpleTestCase
from typesafe_sdk import ChoiceAnswer, TypeSafeError

from workflows.graph.state import build_initial_state

from .decision_model import AlwaysContinueDecisionModel
from .heuristics import match_known_side_query_keywords
from .jev_router import JevDecisionModel, get_jev_decision_model
from .router import route_message


class AlwaysContinueDecisionModelTests(SimpleTestCase):
    def test_always_returns_continue_with_full_confidence(self):
        model = AlwaysContinueDecisionModel()
        state = build_initial_state(conversation_id=1)

        result = model.decide("¿Hacen envíos a Santa Fe?", state)

        self.assertEqual(result["decision"], "CONTINUE")
        self.assertEqual(result["confidence"], 1.0)


class RouteMessageTests(SimpleTestCase):
    def test_records_routing_decision_and_confidence_on_state(self):
        state = build_initial_state(conversation_id=1)

        state = route_message(state, "Busco una notebook gamer.")

        self.assertEqual(state["routing_decision"], "CONTINUE")
        self.assertEqual(state["routing_confidence"], 1.0)


class _FakeTypeSafeClient:
    """Duck-typed stand-in for TypeSafeClient — no real API calls."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.last_call = None

    def system_one(self, **kwargs):
        self.last_call = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeSystemOneResponse:
    def __init__(self, choices):
        self.choices = choices


class JevDecisionModelTests(SimpleTestCase):
    def test_maps_choice_answer_to_routing_result(self):
        answer = ChoiceAnswer(
            type="choice",
            choice="SIDE_QUERY",
            confidence=0.94,
            probabilities={"CONTINUE": 0.04, "SIDE_QUERY": 0.94, "REPLACE": 0.02},
        )
        client = _FakeTypeSafeClient(response=_FakeSystemOneResponse({"routing": answer}))
        model = JevDecisionModel(client=client)
        state = build_initial_state(conversation_id=1)
        state["active_workflow"] = "PRODUCT_PURCHASE"
        state["active_node"] = "PRODUCT_COMPARISON"

        result = model.decide("¿Hacen envíos a Santa Fe?", state)

        self.assertEqual(result, {"decision": "SIDE_QUERY", "confidence": 0.94})
        self.assertEqual(client.last_call["state"]["active_node"], "PRODUCT_COMPARISON")

    def test_falls_back_to_continue_on_api_error(self):
        client = _FakeTypeSafeClient(error=TypeSafeError("invalid key"))
        model = JevDecisionModel(client=client)
        state = build_initial_state(conversation_id=1)

        result = model.decide("¿Hacen envíos a Santa Fe?", state)

        self.assertEqual(result, {"decision": "CONTINUE", "confidence": 1.0})


class GetJevDecisionModelTests(SimpleTestCase):
    def test_falls_back_when_no_api_key_configured(self):
        with self.settings(TYPESAFE_API_KEY=""):
            model = get_jev_decision_model()

        self.assertIsInstance(model, AlwaysContinueDecisionModel)

    def test_uses_jev_when_api_key_configured(self):
        with self.settings(TYPESAFE_API_KEY="test-key-not-real"):
            model = get_jev_decision_model()

        self.assertIsInstance(model, JevDecisionModel)


class MatchKnownSideQueryKeywordsTests(SimpleTestCase):
    def test_matches_shipping_keyword(self):
        self.assertEqual(match_known_side_query_keywords("¿Hacen envíos a Santa Fe?"), "SIDE_QUERY")

    def test_matches_warranty_keyword(self):
        self.assertEqual(match_known_side_query_keywords("¿Tiene garantía?"), "SIDE_QUERY")

    def test_returns_none_when_no_keyword_matches(self):
        self.assertIsNone(match_known_side_query_keywords("Quiero la notebook ASUS."))


class _FixedDecisionModel:
    def __init__(self, decision: str, confidence: float):
        self._result = {"decision": decision, "confidence": confidence}

    def decide(self, message_text, state):
        return self._result


class RouteMessageConfidenceTests(SimpleTestCase):
    def test_high_confidence_decision_is_trusted_as_is(self):
        state = build_initial_state(conversation_id=1)
        model = _FixedDecisionModel("REPLACE", 0.99)

        state = route_message(state, "Olvidate de la notebook, quiero un monitor.", decision_model=model)

        self.assertEqual(state["routing_decision"], "REPLACE")
        self.assertEqual(state["routing_confidence"], 0.99)

    def test_medium_confidence_resolved_by_keyword_heuristic(self):
        state = build_initial_state(conversation_id=1)
        model = _FixedDecisionModel("CONTINUE", 0.7)

        state = route_message(state, "¿Hacen envíos a Santa Fe?", decision_model=model)

        self.assertEqual(state["routing_decision"], "SIDE_QUERY")
        self.assertEqual(state["routing_confidence"], 0.7)

    def test_medium_confidence_without_keyword_match_escalates_and_keeps_original(self):
        state = build_initial_state(conversation_id=1)
        model = _FixedDecisionModel("SIDE_QUERY", 0.7)

        with mock.patch("workflows.routing.router.get_routing_llm_provider") as get_provider:
            get_provider.return_value.decide_routing.return_value = None
            state = route_message(state, "Quiero la notebook ASUS.", decision_model=model)

        self.assertEqual(state["routing_decision"], "SIDE_QUERY")
        self.assertEqual(state["routing_confidence"], 0.7)

    def test_low_confidence_escalates_to_llm(self):
        state = build_initial_state(conversation_id=1)
        model = _FixedDecisionModel("CONTINUE", 0.2)

        with mock.patch("workflows.routing.router.get_routing_llm_provider") as get_provider:
            get_provider.return_value.decide_routing.return_value = {
                "decision": "REPLACE",
                "confidence": 0.9,
            }
            state = route_message(state, "mensaje ambiguo", decision_model=model)

        self.assertEqual(state["routing_decision"], "REPLACE")
        self.assertEqual(state["routing_confidence"], 0.9)

    def test_low_confidence_without_available_escalation_keeps_original(self):
        state = build_initial_state(conversation_id=1)
        model = _FixedDecisionModel("CONTINUE", 0.2)

        state = route_message(state, "mensaje ambiguo", decision_model=model)

        self.assertEqual(state["routing_decision"], "CONTINUE")
        self.assertEqual(state["routing_confidence"], 0.2)
