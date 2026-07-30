from __future__ import annotations

import unittest

from core.light_group_plan import (
    CompositeConnectionDecision,
    GroupAdjustment,
    build_light_group_plan,
    decide_composite_connection,
)


class LightGroupPlanTests(unittest.TestCase):
    def test_residual_then_adjusted_groups(self) -> None:
        plan = build_light_group_plan(
            ["Key", "Fill"],
            {
                "Key": GroupAdjustment("Key", ev=1.0, tint=(1.0, 0.5, 0.25)),
                "Fill": GroupAdjustment("Fill", ev=-1.0),
            },
        )
        operations = [step["operation"] for step in plan["steps"]]
        self.assertEqual(
            operations,
            ["SUBTRACT", "SUBTRACT", "EXPOSURE", "MULTIPLY", "ADD", "EXPOSURE", "MULTIPLY", "ADD"],
        )
        self.assertEqual(plan["groups"][0]["ev"], 1.0)
        self.assertEqual(plan["groups"][0]["tint"], [1.0, 0.5, 0.25])
        self.assertTrue(plan["output"].startswith("sum:"))

    def test_duplicate_names_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_light_group_plan(["Key", "Key"])

    def test_composite_connection_policy(self) -> None:
        self.assertEqual(
            decide_composite_connection(input_is_linked=False, source_is_managed=False),
            CompositeConnectionDecision.CONNECT,
        )
        self.assertEqual(
            decide_composite_connection(input_is_linked=True, source_is_managed=True),
            CompositeConnectionDecision.REPLACE_MANAGED,
        )
        self.assertEqual(
            decide_composite_connection(input_is_linked=True, source_is_managed=False),
            CompositeConnectionDecision.PRESERVE_USER,
        )


if __name__ == "__main__":
    unittest.main()
