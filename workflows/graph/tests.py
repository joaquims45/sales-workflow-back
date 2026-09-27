from django.test import SimpleTestCase

from .state import FunnelStage, build_initial_state
from .transitions import apply_hardcoded_transition


class SalesStateTests(SimpleTestCase):
    def test_initial_state_shape(self):
        state = build_initial_state(conversation_id=1)

        self.assertEqual(state["conversation_id"], 1)
        self.assertEqual(state["funnel_stage"], FunnelStage.DISCOVERY)
        self.assertIsNone(state["primary_goal"])
        self.assertEqual(state["customer_needs"], [])
        self.assertEqual(state["workflow_stack"], [])


class HardcodedTransitionTests(SimpleTestCase):
    def test_sets_primary_goal_on_first_message(self):
        state = build_initial_state(conversation_id=1)

        state = apply_hardcoded_transition(state, "Busco una notebook para programar y jugar.")

        self.assertEqual(state["primary_goal"], "BUY_PRODUCT")
        self.assertEqual(state["active_workflow"], "PRODUCT_PURCHASE")
        self.assertIn("gaming", state["customer_needs"])
        self.assertIn("programming", state["customer_needs"])
        self.assertEqual(state["funnel_stage"], FunnelStage.CONSIDERATION)

    def test_extracts_budget_constraint(self):
        state = build_initial_state(conversation_id=1)

        state = apply_hardcoded_transition(state, "Tengo hasta $1.500.000.")

        self.assertEqual(state["constraints"]["budget_max"], 1500000)

    def test_does_not_duplicate_needs(self):
        state = build_initial_state(conversation_id=1)

        state = apply_hardcoded_transition(state, "quiero jugar")
        state = apply_hardcoded_transition(state, "también quiero jugar mucho")

        self.assertEqual(state["customer_needs"].count("gaming"), 1)
