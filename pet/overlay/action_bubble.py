"""Small transient bubble that shows the pet's narrated actions — text the
model wrapped in *asterisks*, e.g. "*si avvicina e ti tocca la fronte*" —
instead of reading them aloud."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

import config


class ActionBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(220)
        self.label.setStyleSheet(
            "QLabel { background-color: rgba(255, 255, 255, 235);"
            " border-radius: 10px; padding: 8px; font-size: 10pt;"
            " font-style: italic; color: #444; }"
        )

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_action(self, text: str, anchor_x: int, anchor_y: int, screen_rect):
        """Shows `text` anchored above the pet's current position
        (anchor_x/anchor_y = pet's top-left corner), clamped to stay within
        `screen_rect`, and auto-hides after ACTION_BUBBLE_DURATION_MS."""
        self.label.setText(text)
        self.label.adjustSize()
        self.resize(self.label.size())

        x = anchor_x + config.DISPLAY_SIZE // 2 - self.width() // 2
        y = anchor_y - self.height() - 8
        max_x = screen_rect.x() + screen_rect.width() - self.width()
        x = max(screen_rect.x(), min(x, max_x))
        y = max(screen_rect.y(), y)
        self.move(x, y)

        self.show()
        self._hide_timer.start(config.ACTION_BUBBLE_DURATION_MS)
