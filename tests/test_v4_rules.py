import copy
import json
import math
import unittest
from eup_administration.v4.rules import conditions, matches, validate_graph, forecast, positive


class TestPolicyRules(unittest.TestCase):
    def setUp(self):
        self.states = [{"state": "Draft", "sla_hours": 24}, {"state": "Done", "is_terminal": 1}]
        self.transitions = [{"action": "Complete", "from_state": "Draft", "to_state": "Done",
                             "allowed_role": "Administration Manager", "approval_required": 1}]
        self.bands = [{"transition_action": "Complete", "step_number": 1,
                       "approver_role": "Administration Manager", "same_company": 1}]

    def validate(self):
        return validate_graph(self.states, self.transitions, "Draft", self.bands)

    def test_valid_graph(self):
        self.validate()

    def test_unknown_states(self):
        self.transitions[0]["to_state"] = "GL Entry"
        with self.assertRaises(ValueError):
            self.validate()

    def test_unreachable_state(self):
        self.states.append({"state": "Hidden"})
        with self.assertRaises(ValueError):
            self.validate()

    def test_dead_end_cycle(self):
        self.states.append({"state": "Trapped"})
        self.transitions.extend([
            {"action": "Trap", "from_state": "Draft", "to_state": "Trapped", "allowed_role": "Manager"},
            {"action": "Loop", "from_state": "Trapped", "to_state": "Trapped", "allowed_role": "Manager"}
        ])
        with self.assertRaises(ValueError):
            self.validate()

    def test_terminal_cannot_transition(self):
        self.transitions[0]["from_state"] = "Done"
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_action_denied(self):
        self.transitions.append(copy.deepcopy(self.transitions[0]))
        with self.assertRaises(ValueError):
            self.validate()

    def test_approval_numbers_sequential(self):
        self.bands[0]["step_number"] = 2
        with self.assertRaises(ValueError):
            self.validate()

    def test_cross_company_approval_policy_denied(self):
        self.bands[0]["same_company"] = 0
        with self.assertRaises(ValueError):
            self.validate()

    def test_orphan_approval_denied(self):
        self.bands[0]["transition_action"] = "Unknown"
        with self.assertRaises(ValueError):
            self.validate()

    def test_negative_or_nonfinite_sla(self):
        for value in [-1, float("nan"), float("inf")]:
            self.states[0]["sla_hours"] = value
            with self.assertRaises(ValueError):
                self.validate()

    def test_conditions_are_conjunction(self):
        raw = '[{"field":"priority","op":"in","value":["High","Critical"]},{"field":"category","op":"eq","value":"Safety"}]'
        self.assertTrue(matches(raw, {"priority": "High", "category": "Safety"}))
        self.assertFalse(matches(raw, {"priority": "High", "category": "Electrical"}))

    def test_code_sql_and_unknown_fields_rejected(self):
        for raw in ['__import__("os")', '{"sql":"delete"}', '[{"field":"password","op":"eq","value":"x"}]',
                    '[{"field":"priority","op":"eval","value":"x"}]']:
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                conditions(raw)

    def test_condition_limits(self):
        with self.assertRaises(ValueError):
            conditions([{"field": "priority", "op": "eq", "value": "High"}] * 21)
        with self.assertRaises(ValueError):
            conditions([{"field": "priority", "op": "in", "value": ["High"] * 51}])

    def test_forecast_sparse_data(self):
        self.assertFalse(forecast([2] * 6)["available"])

    def test_forecast_accounts_for_zero_days(self):
        result = forecast([0, 0, 7, 0, 0, 0, 0])
        self.assertEqual(result["daily_mean"], 1)
        self.assertEqual(result["expected_quantity"], 7)

    def test_forecast_uses_bounded_window(self):
        result = forecast([100] * 20 + [2] * 28)
        self.assertEqual(result["sample_days"], 28)
        self.assertEqual(result["expected_quantity"], 14)

    def test_bad_consumption_rejected(self):
        for bad in [-1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                forecast([bad] * 7)
