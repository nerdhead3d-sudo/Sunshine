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

    def test_idle_eventually_transitions_to_walking_or_sitting(self):
        sm = PetStateMachine()
        sm._ticks_left = 1
        result = sm.tick(False, False)
        self.assertIn(
            result,
            (State.WALK_LEFT, State.WALK_RIGHT, State.RUN_LEFT, State.RUN_RIGHT, State.SIT, State.PLAY,
             State.TURN_FRONT),
        )

    def test_sit_eventually_transitions_to_idle_or_sleep(self):
        sm = PetStateMachine()
        sm.state = State.SIT
        sm._ticks_left = 1
        result = sm.tick(False, False)
        self.assertIn(result, (State.IDLE, State.SLEEP))

    def test_sleep_eventually_transitions_to_idle(self):
        sm = PetStateMachine()
        sm.state = State.SLEEP
        sm._ticks_left = 1
        result = sm.tick(False, False)
        self.assertEqual(result, State.IDLE)

    def test_drag_has_absolute_priority_until_ended(self):
        sm = PetStateMachine()
        sm.trigger_react(ticks=3)
        sm.start_drag()
        self.assertEqual(sm.state, State.DRAGGED)

        self.assertEqual(sm.tick(False, False), State.DRAGGED)
        self.assertEqual(sm.tick(True, True), State.DRAGGED)

        sm.end_drag()
        self.assertEqual(sm.state, State.IDLE)

    def test_run_left_bounces_to_run_right_at_left_edge(self):
        sm = PetStateMachine()
        sm.state = State.RUN_LEFT
        sm._ticks_left = 100
        self.assertEqual(sm.tick(at_left_edge=True, at_right_edge=False), State.RUN_RIGHT)

    def test_land_plays_for_n_ticks_then_idles(self):
        sm = PetStateMachine()
        sm.start_fall()
        sm.land(ticks=2)
        self.assertEqual(sm.tick(False, False), State.LAND)
        self.assertEqual(sm.tick(False, False), State.IDLE)

    def test_jump_and_fall_are_held_until_changed_externally(self):
        sm = PetStateMachine()
        sm.start_jump()
        for _ in range(50):
            self.assertEqual(sm.tick(False, False), State.JUMP)
        sm.start_fall()
        for _ in range(50):
            self.assertEqual(sm.tick(True, True), State.FALL)

    def test_face_front_holds_while_talking_then_turns_back(self):
        sm = PetStateMachine()
        sm.face_front(hold=True)
        self.assertEqual(sm.state, State.TURN_FRONT)
        for _ in range(20):
            sm.tick(False, False)
        self.assertEqual(sm.state, State.FRONT)
        for _ in range(500):  # held: never turns back on its own
            self.assertEqual(sm.tick(False, False), State.FRONT)

        sm.release_front()
        states = [sm.tick(False, False) for _ in range(60)]
        self.assertIn(State.TURN_BACK, states)
        self.assertEqual(states[-1], State.IDLE)

    def test_sleeping_pet_does_not_turn_when_sunshine_talks(self):
        sm = PetStateMachine()
        sm.state = State.SLEEP
        sm.face_front(hold=True)
        self.assertEqual(sm.state, State.SLEEP)


if __name__ == "__main__":
    unittest.main()
