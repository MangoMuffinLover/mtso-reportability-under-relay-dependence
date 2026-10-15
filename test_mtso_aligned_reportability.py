import unittest
from fractions import Fraction

import mtso_aligned_reportability as pilot


class StructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.visit = staticmethod(lambda selected: pilot.expected_value(selected, pilot.visit_value_in_scenario))
        cls.fixed = staticmethod(lambda selected: pilot.expected_value(selected, pilot.fixed_report_value_in_scenario))
        cls.relay = staticmethod(lambda selected: pilot.expected_value(selected, pilot.relay_report_value_in_scenario))

    def test_all_routes_meet_declared_survival_threshold(self):
        for route in pilot.ROUTES:
            self.assertGreaterEqual(pilot.survival_probability(route), pilot.SURVIVAL_THRESHOLD)

    def test_visitation_is_submodular_on_fixture(self):
        self.assertEqual(pilot.diminishing_returns_audit(self.visit)["violation_count"], 0)

    def test_fixed_reportability_is_submodular_on_fixture(self):
        self.assertEqual(pilot.diminishing_returns_audit(self.fixed)["violation_count"], 0)

    def test_relay_delivery_breaks_diminishing_returns(self):
        audit = pilot.diminishing_returns_audit(self.relay)
        self.assertEqual(audit["violation_count"], 324)
        self.assertEqual(audit["minimum_slack"], "-39/20")

    def test_relay_greedy_gap(self):
        _, greedy_value, _ = pilot.greedy(self.relay)
        optimal_set = pilot.optimum(self.relay)
        optimal_value = self.relay(optimal_set)
        self.assertEqual(greedy_value, Fraction(9, 5))
        self.assertEqual(optimal_value, Fraction(15, 4))
        self.assertEqual(greedy_value / optimal_value, Fraction(12, 25))

    def test_bundle_lift_moves_difficulty_to_feasibility(self):
        self.assertEqual(pilot.bundle_coverage_audit()["violation_count"], 0)
        exchange = pilot.bundle_exchange_audit()
        self.assertGreater(exchange["exchange_violation_count"], 0)
        self.assertEqual(exchange["witness"]["small"], ["bundle_23"])
        self.assertEqual(exchange["witness"]["large"], ["bundle_12", "bundle_34"])


if __name__ == "__main__":
    unittest.main()
