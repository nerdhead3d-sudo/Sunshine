import random
from enum import Enum

import config


class State(Enum):
    IDLE = "idle"
    WALK_LEFT = "walk_left"
    WALK_RIGHT = "walk_right"
    RUN_LEFT = "run_left"
    RUN_RIGHT = "run_right"
    REACT = "react"
    SIT = "sit"
    SLEEP = "sleep"
    PLAY = "play"
    DRAGGED = "dragged"
    JUMP = "jump"
    FALL = "fall"
    LAND = "land"
    TURN_FRONT = "turn_front"
    FRONT = "front"
    TURN_BACK = "turn_back"


# Moving states and their horizontal direction (-1 left, +1 right).
MOVING = {
    State.WALK_LEFT: -1, State.WALK_RIGHT: 1,
    State.RUN_LEFT: -1, State.RUN_RIGHT: 1,
}
_REVERSED = {
    State.WALK_LEFT: State.WALK_RIGHT, State.WALK_RIGHT: State.WALK_LEFT,
    State.RUN_LEFT: State.RUN_RIGHT, State.RUN_RIGHT: State.RUN_LEFT,
}
# States driven from outside (PetWindow's drag/jump/fall physics): tick()
# leaves them alone until the caller moves the machine on explicitly.
_EXTERNAL = (State.DRAGGED, State.JUMP, State.FALL)
# Short one-shot states that count down and then go back to idle.
_TIMED = (State.REACT, State.LAND, State.PLAY)
# States the pet may turn to face the viewer from (when Sunshine starts
# talking): calm ones only — not mid-jump/fall/drag, and a sleeping cat
# stays asleep.
_CAN_FACE_FRONT = (
    State.IDLE, State.WALK_LEFT, State.WALK_RIGHT, State.RUN_LEFT, State.RUN_RIGHT,
    State.SIT, State.REACT, State.PLAY, State.TURN_BACK,
)


class PetStateMachine:
    """Minimal idle/walk/run/sit/sleep/play behavior. Picks a random
    direction to wander in (sometimes running instead of walking), sits
    down for a while, or does a short playful pounce, then idles for a bit,
    reversing direction if it hits a screen edge. Sitting for long enough
    can drift into sleep.

    REACT/LAND/PLAY take over for a fixed number of ticks before returning
    to idle. DRAGGED/JUMP/FALL are forced externally (mouse drag, jumping
    onto a window, falling after a drop) and only end when the caller says
    so — `end_drag()`, `start_fall()`, `land()`.
    """

    def __init__(self):
        self.state = State.IDLE
        self._ticks_left = self._idle_duration()
        self._timed_ticks_left = 0
        self._front_hold = False  # stay facing the viewer until release_front()

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

    def _start_timed(self, state: State, ticks: int):
        self.state = state
        self._timed_ticks_left = ticks

    def trigger_react(self, ticks: int = 30):
        """Forces a greeting reaction for `ticks` movement-ticks, then resumes idling."""
        self._start_timed(State.REACT, ticks)

    def start_drag(self):
        """Forces DRAGGED with absolute priority until `end_drag()` is called."""
        self.state = State.DRAGGED

    def end_drag(self):
        self.state = State.IDLE
        self._ticks_left = self._idle_duration()

    def start_jump(self):
        """Forces JUMP while PetWindow moves the pet along its jump arc."""
        self.state = State.JUMP

    def start_fall(self):
        """Forces FALL while PetWindow applies gravity, until `land()`."""
        self.state = State.FALL

    def land(self, ticks: int = config.LAND_TICKS):
        """Touchdown: plays the landing animation, then resumes idling."""
        self._start_timed(State.LAND, ticks)

    def face_front(self, hold: bool = False):
        """Turns to face the viewer (TURN_FRONT -> FRONT). With `hold` it
        stays that way until `release_front()` — used while Sunshine talks."""
        self._front_hold = self._front_hold or hold
        if self.state in (State.FRONT, State.TURN_FRONT):
            return
        if self.state in _CAN_FACE_FRONT:
            self._start_timed(State.TURN_FRONT, config.TURN_TICKS)

    def release_front(self):
        """Ends a `face_front(hold=True)`: lingers a moment, then turns back."""
        if not self._front_hold:
            return
        self._front_hold = False
        if self.state == State.FRONT:
            self._ticks_left = min(self._ticks_left, config.FRONT_LINGER_TICKS)

    def tick(self, at_left_edge: bool, at_right_edge: bool) -> State:
        if self.state in _EXTERNAL:
            return self.state

        if self.state == State.TURN_FRONT:
            self._timed_ticks_left -= 1
            if self._timed_ticks_left <= 0:
                self.state = State.FRONT
                self._ticks_left = random.randint(*config.FRONT_DURATION_TICKS)
            return self.state

        if self.state == State.FRONT:
            if not self._front_hold:
                self._ticks_left -= 1
                if self._ticks_left <= 0:
                    self._start_timed(State.TURN_BACK, config.TURN_TICKS)
            return self.state

        if self.state == State.TURN_BACK:
            self._timed_ticks_left -= 1
            if self._timed_ticks_left <= 0:
                self.state = State.IDLE
                self._ticks_left = self._idle_duration()
            return self.state

        if self.state in _TIMED:
            self._timed_ticks_left -= 1
            if self._timed_ticks_left <= 0:
                self.state = State.IDLE
                self._ticks_left = self._idle_duration()
            return self.state

        self._ticks_left -= 1
        if self._ticks_left <= 0:
            self._transition()

        direction = MOVING.get(self.state)
        if (direction == -1 and at_left_edge) or (direction == 1 and at_right_edge):
            self.state = _REVERSED[self.state]
            self._ticks_left = self._walk_duration()

        return self.state

    def _transition(self):
        if self.state == State.IDLE:
            roll = random.random()
            if roll < config.SIT_CHANCE:
                self.state = State.SIT
                self._ticks_left = self._sit_duration()
            elif roll < config.SIT_CHANCE + config.PLAY_CHANCE:
                self._start_timed(State.PLAY, config.PLAY_TICKS)
            elif roll < config.SIT_CHANCE + config.PLAY_CHANCE + config.FRONT_CHANCE:
                self._start_timed(State.TURN_FRONT, config.TURN_TICKS)
            else:
                if random.random() < config.RUN_CHANCE:
                    self.state = random.choice([State.RUN_LEFT, State.RUN_RIGHT])
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
