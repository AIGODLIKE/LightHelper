import importlib.util
import math
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "utils" / "placement.py"
SPEC = importlib.util.spec_from_file_location("light_helper_placement_math", MODULE_PATH)
placement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(placement)


class PlacementMathTests(unittest.TestCase):
    def assertVectorAlmostEqual(self, actual, expected, places=7):
        for actual_component, expected_component in zip(actual, expected, strict=True):
            self.assertAlmostEqual(actual_component, expected_component, places=places)

    def test_direct_uses_surface_normal(self):
        solution = placement.solve_placement(
            (1.0, 2.0, 3.0),
            (0.0, 0.0, 2.0),
            (0.0, 0.0, 1.0),
            4.0,
            "DIRECT",
        )
        self.assertVectorAlmostEqual(solution.direction_from_target, (0.0, 0.0, 1.0))
        self.assertVectorAlmostEqual(solution.position, (1.0, 2.0, 7.0))

    def test_reflect_mirrors_view_about_normal(self):
        direction = placement.reflect_light_direction((1.0, 0.0, 1.0), (0.0, 0.0, 1.0))
        root_half = math.sqrt(0.5)
        self.assertVectorAlmostEqual(direction, (-root_half, 0.0, root_half))

    def test_reflect_faces_a_backfacing_normal_toward_view(self):
        direction = placement.reflect_light_direction((0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
        self.assertVectorAlmostEqual(direction, (0.0, 0.0, 1.0))

    def test_orbit_preserves_given_radial_direction(self):
        solution = placement.solve_placement(
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, -1.0, 1.0),
            3.0,
            placement.PlacementMode.ORBIT,
            (2.0, 0.0, 0.0),
        )
        self.assertVectorAlmostEqual(solution.position, (3.0, 0.0, 0.0))

    def test_cursor_plane_fallback_intersects_in_front(self):
        point = placement.ray_plane_intersection(
            (0.0, 0.0, 10.0),
            (0.0, 0.0, -1.0),
            (2.0, 3.0, 0.0),
            (0.0, 0.0, 1.0),
        )
        self.assertVectorAlmostEqual(point, (0.0, 0.0, 0.0))

    def test_cursor_plane_fallback_rejects_parallel_and_behind(self):
        self.assertIsNone(placement.ray_plane_intersection(
            (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0),
        ))
        self.assertIsNone(placement.ray_plane_intersection(
            (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0),
        ))

    def test_adaptive_dimensions_have_practical_minimums(self):
        self.assertEqual(placement.adaptive_size_distance(0.0), (0.25, 1.0))
        self.assertEqual(placement.adaptive_size_distance(4.0), (2.0, 6.0))

    def test_wheel_adjustments_are_bounded(self):
        self.assertAlmostEqual(placement.adjust_energy(100.0, 4), 200.0)
        self.assertGreater(placement.adjust_size(1.0, 1), 1.0)
        self.assertGreater(placement.adjust_distance(1.0, 1), 1.0)
        self.assertEqual(placement.adjust_spot_size(math.pi, 10), math.pi)
        self.assertAlmostEqual(placement.adjust_roll(0.0, 1), math.pi / 36.0)


if __name__ == "__main__":
    unittest.main()
