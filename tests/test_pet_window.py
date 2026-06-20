"""Unit tests for PetWindow's pure landing/drag logic. Built via
PetWindow.__new__ (skips Qt's __init__/widget construction entirely) with
the handful of attributes those methods actually touch, plus no-op stubs
for the two calls that need a real Qt widget (_update_pixmap, update) —
this keeps the tests fast and display-less without needing a QApplication
or the real animator/sprite files."""

import unittest

import config
from pet.behavior.state_machine import PetStateMachine, State
from pet.overlay.pet_window import PetWindow


def _make_window(x=100, y=50, ground_y=800, platforms=None):
    win = PetWindow.__new__(PetWindow)
    win._x = x
    win._y = y
    win._ground_y = ground_y
    win._platforms = platforms or []
    win._on_platform = False
    win._platform_bounds = None
    win._falling = False
    win.frame_index = 0
    win._last_state = None
    win.state_machine = PetStateMachine()
    win._update_pixmap = lambda: None  # avoid touching the real sprite animator
    win.update = lambda: None  # avoid requiring a real QWidget/QApplication
    return win


class ComputeLandingTests(unittest.TestCase):
    def test_falls_to_ground_with_no_windows(self):
        win = _make_window()
        landing_y, bounds = win._compute_landing()
        self.assertEqual(landing_y, win._ground_y)
        self.assertIsNone(bounds)

    def test_lands_on_window_directly_below_with_enough_overlap(self):
        win = _make_window(x=100, y=50, ground_y=800, platforms=[(0, 400, 300)])
        landing_y, bounds = win._compute_landing()
        self.assertEqual(landing_y, 300 - config.DISPLAY_SIZE)
        self.assertEqual(bounds, (0, 400))

    def test_ignores_window_with_too_little_horizontal_overlap(self):
        # pet footprint is [100, 100+DISPLAY_SIZE); a window starting at 380
        # only overlaps by 20px, well under the 50%-of-width threshold.
        win = _make_window(x=100, y=50, ground_y=800, platforms=[(380, 400, 300)])
        landing_y, bounds = win._compute_landing()
        self.assertEqual(landing_y, win._ground_y)
        self.assertIsNone(bounds)

    def test_ignores_window_above_current_position(self):
        win = _make_window(x=100, y=50, ground_y=800, platforms=[(0, 400, 10)])
        landing_y, bounds = win._compute_landing()
        self.assertEqual(landing_y, win._ground_y)
        self.assertIsNone(bounds)

    def test_picks_nearest_window_when_several_are_below(self):
        win = _make_window(x=100, y=50, ground_y=800, platforms=[(0, 400, 600), (0, 400, 300)])
        landing_y, bounds = win._compute_landing()
        self.assertEqual(landing_y, 300 - config.DISPLAY_SIZE)
        self.assertEqual(bounds, (0, 400))


class LandTests(unittest.TestCase):
    def test_landing_on_ground_clears_platform_state(self):
        win = _make_window(platforms=[])
        win._on_platform = True
        win._platform_bounds = (0, 400)

        win._land(win._ground_y, None)

        self.assertEqual(win._y, win._ground_y)
        self.assertFalse(win._falling)
        self.assertFalse(win._on_platform)
        self.assertIsNone(win._platform_bounds)
        self.assertEqual(win.state_machine.state, State.REACT)

    def test_landing_on_a_window_sets_platform_state(self):
        win = _make_window()
        win._land(108, (0, 400))

        self.assertEqual(win._y, 108)
        self.assertTrue(win._on_platform)
        self.assertEqual(win._platform_bounds, (0, 400))


if __name__ == "__main__":
    unittest.main()
