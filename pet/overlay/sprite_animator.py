from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QTransform

import config

# States only the sprite sheet provides frames for: with the procedural
# placeholders (no sheet) they borrow the closest existing animation instead
# of drawing nothing.
_FALLBACK_STATES = {
    "run_left": "walk_left",
    "run_right": "walk_right",
    "jump": "react",
    "land": "react",
    "play": "react",
    "fall": "dragged",
    # facing the viewer only exists in the 3D renders
    "turn_front": "idle",
    "front": "idle",
    "turn_back": "idle",
}


class SpriteAnimator:
    """Loads sprite frame PNGs per state and serves them as scaled QPixmaps."""

    def __init__(self):
        self._cache = {}
        self._mirrored_cache = {}

    def _load_state(self, state: str):
        if state not in self._cache:
            frame_dir = config.SPRITES_DIR / state
            # Numeric order: a plain sort would put state_10 before state_2.
            files = sorted(frame_dir.glob(f"{state}_*.png"), key=lambda f: int(f.stem.rsplit("_", 1)[1]))
            if not files and state in _FALLBACK_STATES:
                self._cache[state] = self._load_state(_FALLBACK_STATES[state])
                return self._cache[state]
            pixmaps = []
            for f in files:
                pm = QPixmap(str(f))
                pm = pm.scaled(
                    config.DISPLAY_SIZE,
                    config.DISPLAY_SIZE,
                    Qt.KeepAspectRatio,
                    # Smooth, not nearest-neighbour: the sprite-sheet frames
                    # are detailed renders scaled *down*, not pixel art.
                    Qt.SmoothTransformation,
                )
                pixmaps.append(pm)
            self._cache[state] = pixmaps
        return self._cache[state]

    def _load_mirrored(self, state: str):
        if state not in self._mirrored_cache:
            flip = QTransform().scale(-1, 1)
            self._mirrored_cache[state] = [pm.transformed(flip) for pm in self._load_state(state)]
        return self._mirrored_cache[state]

    def get_frame(self, state: str, index: int, mirrored: bool = False) -> QPixmap | None:
        frames = self._load_mirrored(state) if mirrored else self._load_state(state)
        if not frames:
            return None
        return frames[index % len(frames)]

    def frame_count(self, state: str) -> int:
        return len(self._load_state(state))
