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
    win._jumping = False
    win._dragging = False
    win._climb_id = 0
    win.frame_index = 0
    win._last_state = None
    win.state_machine = PetStateMachine()
    win._update_pixmap = lambda: None  # avoid touching the real sprite animator
    win.update = lambda: None  # avoid requiring a real QWidget/QApplication
    win.move = lambda x, y: None
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
        self.assertEqual(win.state_machine.state, State.LAND)

    def test_landing_on_a_window_sets_platform_state(self):
        win = _make_window()
        win._land(108, (0, 400))

        self.assertEqual(win._y, 108)
        self.assertTrue(win._on_platform)
        self.assertEqual(win._platform_bounds, (0, 400))


class JumpAndClimbDownTests(unittest.TestCase):
    def test_jump_arc_ends_standing_on_the_target_window(self):
        win = _make_window(x=100, y=800, ground_y=800)
        win._jumping = True
        win._jump_tick = 0
        win._jump_from = (100, 800)
        win._jump_to = (150, 300 - config.DISPLAY_SIZE)
        win._jump_target_platform = (0, 600)
        win.state_machine.start_jump()

        peak = win._y
        for _ in range(config.JUMP_TICKS):
            win._tick()
            peak = min(peak, win._y)

        self.assertFalse(win._jumping)
        self.assertEqual((win._x, win._y), (150, 300 - config.DISPLAY_SIZE))
        self.assertTrue(win._on_platform)
        self.assertEqual(win.state_machine.state, State.LAND)
        # the arc rises above the straight line, i.e. above the target itself
        self.assertLess(peak, 300 - config.DISPLAY_SIZE)

    def test_climb_down_falls_to_the_ground(self):
        win = _make_window(x=100, y=100, ground_y=800)
        win._on_platform = True
        win._platform_bounds = (0, 600)

        win._climb_down()

        self.assertTrue(win._falling)
        self.assertFalse(win._on_platform)
        self.assertEqual(win._fall_target_y, 800)
        self.assertEqual(win.state_machine.state, State.FALL)


class PlatformSupportTests(unittest.TestCase):
    def _standing_on_window(self, platforms_now):
        top = 400
        win = _make_window(x=100, y=top - config.DISPLAY_SIZE, ground_y=800, platforms=[(0, 900, top)])
        win._on_platform = True
        win._platform_bounds = (0, 900)
        win._refresh_platforms = lambda: setattr(win, "_platforms", platforms_now)
        return win

    def test_stays_while_the_window_is_still_there(self):
        win = self._standing_on_window([(0, 700, 400)])  # resized, same top
        win._check_platform_support()
        self.assertTrue(win._on_platform)
        self.assertFalse(win._falling)
        self.assertEqual(win._platform_bounds, (0, 700))

    def test_falls_to_the_ground_when_the_window_is_minimized(self):
        win = self._standing_on_window([])
        win._check_platform_support()
        self.assertFalse(win._on_platform)
        self.assertTrue(win._falling)
        self.assertEqual(win._fall_target_y, 800)
        self.assertEqual(win.state_machine.state, State.FALL)

    def test_falls_onto_a_lower_window_when_the_window_moves_down(self):
        win = self._standing_on_window([(0, 900, 600)])  # same window, dragged 200px lower
        win._check_platform_support()
        self.assertTrue(win._falling)
        self.assertEqual(win._fall_target_y, 600 - config.DISPLAY_SIZE)
        self.assertEqual(win._fall_target_platform, (0, 900))


if __name__ == "__main__":
    unittest.main()
