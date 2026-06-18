from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

import config


class SpriteAnimator:
    """Loads sprite frame PNGs per state and serves them as scaled QPixmaps."""

    def __init__(self):
        self._cache = {}

    def _load_state(self, state: str):
        if state not in self._cache:
            frame_dir = config.SPRITES_DIR / state
            files = sorted(frame_dir.glob(f"{state}_*.png"))
            pixmaps = []
            for f in files:
                pm = QPixmap(str(f))
                pm = pm.scaled(
                    config.DISPLAY_SIZE,
                    config.DISPLAY_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
                pixmaps.append(pm)
            self._cache[state] = pixmaps
        return self._cache[state]

    def get_frame(self, state: str, index: int) -> QPixmap | None:
        frames = self._load_state(state)
        if not frames:
            return None
        return frames[index % len(frames)]

    def frame_count(self, state: str) -> int:
        return len(self._load_state(state))
