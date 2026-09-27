from django.test import SimpleTestCase

from workflows.graph.state import build_initial_state

from .decision_model import AlwaysContinueDecisionModel
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
