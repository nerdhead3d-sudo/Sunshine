"""Small, persistent indicator that always shows what the voice loop is
currently doing — listening, thinking, speaking, or muted. Added because
the local LLM/STT pipeline is slow enough (several seconds of silence
between "you stopped talking" and "the pet starts answering") that
without any feedback the user can't tell whether Sunshine heard them at
all or is just unresponsive. Unlike ActionBubble (narrated *actions*,
auto-hides after a few seconds), this never hides — it always reflects
the current state, even if that state is "listening" most of the time."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

import config

_STATUS_STYLE = {
    "listening": ("👂 in ascolto", "rgba(220, 255, 220, 235)", "#1a6b1a"),
    "thinking": ("💭 ci penso...", "rgba(255, 245, 200, 235)", "#8a6d00"),
    "speaking": ("🗣️ ti parlo", "rgba(210, 230, 255, 235)", "#1a4a8a"),
    "muted": ("🔇 microfono muto", "rgba(230, 230, 230, 235)", "#555555"),
}


class StatusBadge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.label = QLabel(self)
        self.label.setMaximumWidth(160)
        self._status = "listening"
        self._apply_style()
        self.show()

    def _apply_style(self):
        text, bg, fg = _STATUS_STYLE[self._status]
        self.label.setText(text)
        self.label.setStyleSheet(
            f"QLabel {{ background-color: {bg}; border-radius: 8px;"
            f" padding: 4px 8px; font-size: 8pt; color: {fg}; }}"
        )
        self.label.adjustSize()
        self.resize(self.label.size())

    def set_status(self, status: str):
        if status not in _STATUS_STYLE or status == self._status:
            return
        self._status = status
        self._apply_style()

    def reposition(self, anchor_x: int, anchor_y: int, screen_rect):
        """Keeps the badge pinned just above-right of the pet's current
        position (anchor_x/anchor_y = pet's top-left corner), clamped to
        the screen — called every animation tick so it follows the pet
        around like a little status light."""
        x = anchor_x + config.DISPLAY_SIZE - self.width() // 2
        y = anchor_y - self.height() - 4
        max_x = screen_rect.x() + screen_rect.width() - self.width()
        x = max(screen_rect.x(), min(x, max_x))
        y = max(screen_rect.y(), y)
        self.move(x, y)
