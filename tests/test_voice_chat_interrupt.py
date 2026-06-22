"""Unit tests for VoiceChatController.interrupt() — built via __new__ with
just the attributes that method touches, so it doesn't need a real
microphone/TTS backend."""

import unittest

from PySide6.QtCore import QObject

import pet.overlay.voice_chat as voice_chat


def _make_controller():
    ctrl = voice_chat.VoiceChatController.__new__(voice_chat.VoiceChatController)
    QObject.__init__(ctrl)
    ctrl._busy = False
    ctrl._speak_queue = []
    ctrl._streaming = False
    ctrl._speaking = False
    ctrl._speak_worker = None
    ctrl._interrupted = False
    ctrl._muted = False
    ctrl._last_status = ""
    ctrl._listener = type("FakeListener", (), {"pause": lambda self: None, "resume": lambda self: None})()
    return ctrl


class InterruptTests(unittest.TestCase):
    def test_returns_false_when_nothing_is_happening(self):
        ctrl = _make_controller()
        self.assertFalse(ctrl.interrupt())

    def test_stops_streaming_and_speaking_and_clears_the_queue(self):
        ctrl = _make_controller()
        ctrl._busy = True
        ctrl._streaming = True
        ctrl._speaking = True
        ctrl._speak_queue = ["frase 1", "frase 2"]

        self.assertTrue(ctrl.interrupt())
        self.assertEqual(ctrl._speak_queue, [])
        self.assertFalse(ctrl._streaming)
        self.assertFalse(ctrl._speaking)
        self.assertFalse(ctrl._busy)
        self.assertTrue(ctrl._interrupted)

    def test_stale_chunk_after_interrupt_is_ignored(self):
        ctrl = _make_controller()
        ctrl._busy = True
        ctrl._streaming = True
        ctrl.interrupt()

        ctrl._reply_buffer = ""
        ctrl._on_reply_chunk("testo che non dovrebbe essere accodato")
        self.assertEqual(ctrl._reply_buffer, "")

    def test_stale_finished_signal_after_interrupt_does_not_reactivate_busy(self):
        ctrl = _make_controller()
        ctrl._busy = True
        ctrl._streaming = True
        ctrl.interrupt()

        ctrl._reply_worker = None
        ctrl._reply_buffer = "frase rimasta in sospeso."
        ctrl._on_reply_finished()
        self.assertFalse(ctrl._busy)


if __name__ == "__main__":
    unittest.main()
