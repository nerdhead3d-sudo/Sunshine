import unittest

from pet.behavior.state_machine import PetStateMachine, State


class PetStateMachineTests(unittest.TestCase):
    def test_starts_idle(self):
        sm = PetStateMachine()
        self.assertEqual(sm.state, State.IDLE)

    def test_trigger_react_overrides_state_for_n_ticks(self):
        sm = PetStateMachine()
        sm.trigger_react(ticks=3)
        self.assertEqual(sm.state, State.REACT)

        self.assertEqual(sm.tick(False, False), State.REACT)
        self.assertEqual(sm.tick(False, False), State.REACT)
        # the third tick exhausts the counter and falls back to idle
        self.assertEqual(sm.tick(False, False), State.IDLE)

    def test_walk_left_bounces_to_walk_right_at_left_edge(self):
        sm = PetStateMachine()
        sm.state = State.WALK_LEFT
        sm._ticks_left = 100  # avoid an unrelated idle/walk transition firing first
        result = sm.tick(at_left_edge=True, at_right_edge=False)
        self.assertEqual(result, State.WALK_RIGHT)

    def test_walk_right_bounces_to_walk_left_at_right_edge(self):
        sm = PetStateMachine()
        sm.state = State.WALK_RIGHT
        sm._ticks_left = 100
        result = sm.tick(at_left_edge=False, at_right_edge=True)
        self.assertEqual(result, State.WALK_LEFT)

    def test_idle_eventually_transitions_to_walking(self):
        sm = PetStateMachine()
        sm._ticks_left = 1
        result = sm.tick(False, False)
        self.assertIn(result, (State.WALK_LEFT, State.WALK_RIGHT))


if __name__ == "__main__":
    unittest.main()
