import random
from enum import Enum

import config


class State(Enum):
    IDLE = "idle"
    WALK_LEFT = "walk_left"
    WALK_RIGHT = "walk_right"
    REACT = "react"
    SIT = "sit"
    SLEEP = "sleep"
    DRAGGED = "dragged"


class PetStateMachine:
    """Minimal idle/walk/sit/sleep behavior. Picks a random direction to
    wander in, or sits down for a while, then idles for a bit, reversing
    direction if it hits a screen edge. Sitting for long enough can drift
    into sleep. A REACT state can be triggered externally (e.g. on webcam
    recognition) and takes over for a fixed number of ticks before
    returning to idle. DRAGGED is forced externally while the user holds
    the pet with the mouse and only ends when `end_drag()` is called.
    """

    def __init__(self):
        self.state = State.IDLE
        self._ticks_left = self._idle_duration()
        self._react_ticks_left = 0

    @staticmethod
    def _idle_duration() -> int:
        return random.randint(40, 100)

    @staticmethod
    def _walk_duration() -> int:
        return random.randint(20, 60)

    @staticmethod
    def _sit_duration() -> int:
        return random.randint(*config.SIT_DURATION_TICKS)

    @staticmethod
    def _sleep_duration() -> int:
        return random.randint(*config.SLEEP_DURATION_TICKS)

    def trigger_react(self, ticks: int = 30):
        """Forces a greeting reaction for `ticks` movement-ticks, then resumes idling."""
        self.state = State.REACT
        self._react_ticks_left = ticks

    def start_drag(self):
        """Forces DRAGGED with absolute priority until `end_drag()` is called."""
        self.state = State.DRAGGED

    def end_drag(self):
        self.state = State.IDLE
        self._ticks_left = self._idle_duration()

    def tick(self, at_left_edge: bool, at_right_edge: bool) -> State:
        if self.state == State.DRAGGED:
            return self.state

        if self.state == State.REACT:
            self._react_ticks_left -= 1
            if self._react_ticks_left <= 0:
                self.state = State.IDLE
                self._ticks_left = self._idle_duration()
            return self.state

        self._ticks_left -= 1
        if self._ticks_left <= 0:
            self._transition()

        if self.state == State.WALK_LEFT and at_left_edge:
            self.state = State.WALK_RIGHT
            self._ticks_left = self._walk_duration()
        elif self.state == State.WALK_RIGHT and at_right_edge:
            self.state = State.WALK_LEFT
            self._ticks_left = self._walk_duration()

        return self.state

    def _transition(self):
        if self.state == State.IDLE:
            if random.random() < config.SIT_CHANCE:
                self.state = State.SIT
                self._ticks_left = self._sit_duration()
            else:
                self.state = random.choice([State.WALK_LEFT, State.WALK_RIGHT])
                self._ticks_left = self._walk_duration()
        elif self.state == State.SIT:
            if random.random() < config.SLEEP_CHANCE:
                self.state = State.SLEEP
                self._ticks_left = self._sleep_duration()
            else:
                self.state = State.IDLE
                self._ticks_left = self._idle_duration()
        else:
            self.state = State.IDLE
            self._ticks_left = self._idle_duration()
