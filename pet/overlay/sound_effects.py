"""Plays the pet's short sound effects (pet/assets/generate_sounds.py).

QSoundEffect rather than winsound: the TTS voice already plays through
winsound.PlaySound, which has a single channel — a meow played that way
would cut Sunshine off mid-sentence. QSoundEffect mixes independently.
"""
import wave

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

import config
from pet import settings_store
from pet.assets import generate_sounds
from pet.logging_setup import get_logger

# "Vocal" sounds stay quiet while Sunshine is talking/thinking, so they don't
# talk over it; physical ones (jump, landing) always play.
_VOCAL = {"meow", "mew", "trill", "purr", "fall_meow"}
# Sounds up to this long are filtered out by the voice listener on their
# own (shorter than config.VAD_MIN_SPEECH_SECONDS); longer ones pause it.
_SAFE_SECONDS = 0.35


class SoundEffects:
    def __init__(self, is_speaking=lambda: False, hold_listening=lambda ms: None):
        self._is_speaking = is_speaking
        self._hold_listening = hold_listening
        self._durations = {}
        self._enabled = bool(settings_store.load().get("sound_effects", True))
        self._effects = {}
        try:
            generate_sounds.ensure(config.SOUNDS_DIR)
            for name in generate_sounds.SOUNDS:
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(str(config.SOUNDS_DIR / f"{name}.wav")))
                effect.setVolume(config.SOUND_EFFECTS_VOLUME)
                self._effects[name] = effect
                with wave.open(str(config.SOUNDS_DIR / f"{name}.wav"), "rb") as w:
                    self._durations[name] = w.getnframes() / w.getframerate()
        except Exception:
            # Never let a missing audio device/codec take the pet down:
            # it just stays silent.
            get_logger().warning("Effetti sonori non disponibili", exc_info=True)
            self._effects = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        settings = settings_store.load()
        settings["sound_effects"] = enabled
        settings_store.save(settings)

    def play(self, name: str):
        if not self._enabled:
            return
        if name in _VOCAL and self._is_speaking():
            return
        effect = self._effects.get(name)
        if effect is None:
            return
        seconds = self._durations.get(name, 0.0)
        if seconds > _SAFE_SECONDS:
            # Long enough to be mistaken for speech by the microphone: mute
            # listening while it plays, plus a little tail for the echo.
            self._hold_listening(int(seconds * 1000) + 300)
        effect.play()
