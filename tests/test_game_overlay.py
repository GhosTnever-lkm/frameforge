from __future__ import annotations

import unittest

from frameforge.core.game_overlay import place_overlay


class OverlayPlacementTests(unittest.TestCase):
    def test_places_panel_at_game_window_top_right_with_negative_monitor_origin(self):
        self.assertEqual(
            place_overlay((-1920, 80, 1280, 720), (380, 500)),
            (-1036, 96, 380, 500),
        )

    def test_clamps_panel_to_small_game_window(self):
        self.assertEqual(
            place_overlay((10, 20, 420, 360), (700, 600)),
            (26, 36, 388, 328),
        )

    def test_rejects_game_window_too_small_for_margins(self):
        self.assertIsNone(place_overlay((0, 0, 20, 100), (200, 200)))
        self.assertIsNone(place_overlay((0, 0, 100, 20), (50, 10)))

    def test_rejects_nonpositive_panel_size(self):
        self.assertIsNone(place_overlay((0, 0, 800, 600), (0, 200)))
        self.assertIsNone(place_overlay((0, 0, 800, 600), (200, -1)))


if __name__ == "__main__":
    unittest.main()
