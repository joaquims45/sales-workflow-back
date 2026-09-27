from django.test import SimpleTestCase
from typesafe_sdk import ChoiceAnswer, TypeSafeError

from workflows.graph.state import build_initial_state

from .decision_model import AlwaysContinueDecisionModel
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
