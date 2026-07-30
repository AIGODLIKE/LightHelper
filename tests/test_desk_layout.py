import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "utils" / "desk_layout.py"
SPEC = importlib.util.spec_from_file_location("light_helper_desk_layout_test", MODULE_PATH)
desk_layout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(desk_layout)


class VisibleMatrixTests(unittest.TestCase):
    def test_large_matrix_lays_out_only_visible_ranges(self):
        rows = desk_layout.visible_slice(100, 27 * 40, 27 * 12, 27)
        columns = desk_layout.visible_slice(300, 86 * 120, 86 * 10, 86)
        self.assertLessEqual(rows.count, 14)
        self.assertLessEqual(columns.count, 12)
        self.assertLessEqual(rows.start, 40)
        self.assertGreater(rows.stop, 40)
        self.assertLessEqual(columns.start, 120)
        self.assertGreater(columns.stop, 120)

    def test_scroll_clamps_both_ends(self):
        self.assertEqual(desk_layout.clamp_scroll(-500, 10, 20, 100), 0)
        self.assertEqual(desk_layout.clamp_scroll(500, 10, 20, 100), 100)

    def test_zero_items_produces_empty_range(self):
        visible = desk_layout.visible_slice(0, 10, 500, 20)
        self.assertEqual((visible.start, visible.stop, visible.count), (0, 0, 0))


class SelectionTests(unittest.TestCase):
    def test_ctrl_toggle_and_shift_replace(self):
        selection = desk_layout.RangeSelection()
        selection.select(2)
        selection.select(4, ctrl=True)
        self.assertEqual(selection.normalized(10), (2, 4))
        selection.select(7, shift=True)
        self.assertEqual(selection.normalized(10), (4, 5, 6, 7))
        selection.select(5, ctrl=True)
        self.assertEqual(selection.normalized(10), (4, 6, 7))

    def test_matrix_selection_cartesian_product(self):
        selection = desk_layout.MatrixSelection()
        selection.rows.values.update((1, 3))
        selection.columns.values.update((2, 5))
        self.assertEqual(
            selection.selected_cells(10, 10),
            ((1, 2), (1, 5), (3, 2), (3, 5)),
        )

    def test_filtered_indexes_keep_source_identity(self):
        entries = (
            desk_layout.LinkTargetSnapshot("Hero", "OBJECT"),
            desk_layout.LinkTargetSnapshot("Hero Collection", "COLLECTION"),
            desk_layout.LinkTargetSnapshot("Background", "OBJECT"),
        )
        self.assertEqual(desk_layout.filter_indices(entries, "hero", "OBJECT"), (0,))
        self.assertEqual(desk_layout.filter_indices(entries, "hero", "COLLECTION"), (1,))


class HitTokenTests(unittest.TestCase):
    def test_stale_frame_geometry_is_rejected(self):
        rect = desk_layout.Rect(0, 0, 20, 20)
        hits = (desk_layout.HitRegion(4, rect, "CELL", (1, 2)),)
        self.assertIsNone(desk_layout.hit_test(hits, 5, 10, 10))
        self.assertEqual(desk_layout.hit_test(hits, 4, 10, 10).payload, (1, 2))

    def test_layout_token_never_returns_zero(self):
        self.assertEqual(desk_layout.next_layout_token(0x7FFFFFFF), 1)


class MixerMathTests(unittest.TestCase):
    def test_kelvin_is_bounded_and_scene_linear(self):
        self.assertEqual(
            desk_layout.kelvin_to_linear_rgb(100),
            desk_layout.kelvin_to_linear_rgb(1000),
        )
        self.assertEqual(
            desk_layout.kelvin_to_linear_rgb(80000),
            desk_layout.kelvin_to_linear_rgb(40000),
        )
        warm = desk_layout.kelvin_to_linear_rgb(2000)
        daylight = desk_layout.kelvin_to_linear_rgb(6500)
        self.assertGreater(warm[0], warm[2])
        self.assertGreater(daylight[2], warm[2])
        self.assertTrue(all(0.0 <= value <= 1.0 for value in daylight))

    def test_ev_and_tint_are_deterministic(self):
        self.assertEqual(desk_layout.apply_ev(100.0, 2.0), 400.0)
        self.assertEqual(desk_layout.apply_ev(100.0, -1.0), 50.0)
        self.assertEqual(
            desk_layout.apply_linear_tint((0.5, 0.5, 0.5), (2.0, 0.5, 0.0)),
            (1.0, 0.25, 0.0),
        )

    def test_column_sets_expand_monotonically(self):
        minimal = set(desk_layout.MIXER_COLUMN_SETS["MINIMAL"])
        normal = set(desk_layout.MIXER_COLUMN_SETS["NORMAL"])
        advanced = set(desk_layout.MIXER_COLUMN_SETS["ADVANCED"])
        self.assertLess(minimal, normal)
        self.assertLess(normal, advanced)
        self.assertIn("normalize", advanced)


if __name__ == "__main__":
    unittest.main()
