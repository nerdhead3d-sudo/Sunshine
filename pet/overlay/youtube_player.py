"""A small embedded YouTube player window (Lumo-style), opened on voice
command ("cerca su youtube gatti"). Unlike the pet's own overlay, this is
a normal titled/closable window — it shows real video content, so it
can't be transparent/click-through, and the user needs an obvious way to
close it. Playback control (play/pause) works by running a tiny snippet
of JavaScript against the page's own <video> element, rather than
integrating the full YouTube IFrame API — good enough for simple voice
commands, much less code."""

from urllib.parse import quote

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

_SEARCH_URL = "https://www.youtube.com/results?search_query={query}"

_PLAY_JS = "(function(){var v=document.querySelector('video'); if(v) v.play();})();"
_PAUSE_JS = "(function(){var v=document.querySelector('video'); if(v) v.pause();})();"


class YouTubePlayerWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YouTube")
        self.resize(900, 600)

        self._view = QWebEngineView(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def search(self, query: str):
        url = _SEARCH_URL.format(query=quote(query))
        self._view.setUrl(QUrl(url))
        self.show()
        self.raise_()
        self.activateWindow()

    def play(self):
        if self.isVisible():
            self._view.page().runJavaScript(_PLAY_JS)

    def pause(self):
        if self.isVisible():
            self._view.page().runJavaScript(_PAUSE_JS)

    def close_player(self):
        self.hide()
