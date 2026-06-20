"""Text-to-speech with a three-tier fallback, run off the UI thread:

1. edge-tts (Microsoft Edge's online neural voices) — best quality, needs
   internet.
2. Piper (offline neural voice, ONNX) — good quality, fully local, used
   automatically when there's no internet. The voice model (~60MB per
   language) is downloaded once from Hugging Face on first use.
3. pyttsx3/SAPI5 — offline but robotic, last-resort fallback if Piper
   itself fails to load.

Each tier picks its voice from config.TTS_VOICES / PIPER_VOICE_BASENAMES /
TTS_FALLBACK_VOICE_HINTS based on the requested language. Whichever tier
is used, `finished_speaking` always fires so the rest of the app doesn't
get stuck waiting; failures are logged to pet/data/pet.log.
"""

import asyncio
import ctypes
import io
import os
import re
import tempfile
import threading
import wave
from pathlib import Path

from PySide6.QtCore import QObject, Signal

import config
from pet.logging_setup import get_logger

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)

_piper_voices: dict[str, object] = {}  # lang -> PiperVoice, or False if it failed to load
_piper_lock = threading.Lock()


def stop_playback():
    """Best-effort: stops whatever is currently playing (the edge-tts/MCI
    path or the Piper/winsound path), so a click can interrupt the pet
    mid-sentence. pyttsx3 (the last-resort fallback) isn't interruptible
    this way — acceptable since it's rarely reached."""
    try:
        ctypes.windll.winmm.mciSendStringW("stop pet_tts_clip", None, 0, None)
    except Exception:
        pass
    try:
        import winsound

        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def clean_for_speech(text: str) -> str:
    """Strips markdown formatting and emoji so the TTS engine doesn't read
    out symbols like '*' or '#' as words."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"[*_`#~]+", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = _EMOJI_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _get_piper_voice(lang: str):
    cached = _piper_voices.get(lang)
    if cached is not None:
        return cached or None
    with _piper_lock:
        cached = _piper_voices.get(lang)
        if cached is not None:
            return cached or None
        try:
            from huggingface_hub import hf_hub_download
            from piper.voice import PiperVoice

            config.PIPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            base = config.PIPER_VOICE_BASENAMES[lang]
            onnx_path = hf_hub_download(
                repo_id=config.PIPER_VOICE_REPO, filename=f"{base}.onnx", local_dir=str(config.PIPER_MODEL_DIR)
            )
            json_path = hf_hub_download(
                repo_id=config.PIPER_VOICE_REPO, filename=f"{base}.onnx.json", local_dir=str(config.PIPER_MODEL_DIR)
            )
            voice = PiperVoice.load(onnx_path, config_path=json_path)
        except Exception:
            get_logger().exception("Failed to load the offline Piper voice for '%s'", lang)
            voice = False
        _piper_voices[lang] = voice
    return voice or None


class SpeakWorker(QObject):
    """Synthesizes and plays `text` (in `lang`) on a background thread."""

    finished_speaking = Signal()

    def __init__(self, text: str, lang: str = config.DEFAULT_LANGUAGE, parent=None):
        super().__init__(parent)
        self._text = clean_for_speech(text)
        self._lang = lang if lang in config.SUPPORTED_LANGUAGES else config.DEFAULT_LANGUAGE

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            mp3_path = asyncio.run(self._synthesize())
            try:
                self._play_mp3(mp3_path)
            finally:
                mp3_path.unlink(missing_ok=True)
        except Exception:
            get_logger().warning(
                "edge-tts failed (likely no internet); trying offline neural voice (Piper)", exc_info=True
            )
            if not self._speak_piper():
                get_logger().warning("Piper unavailable; falling back to robotic offline voice (pyttsx3)")
                self._speak_pyttsx3()
        self.finished_speaking.emit()

    def _speak_piper(self) -> bool:
        voice = _get_piper_voice(self._lang)
        if voice is None:
            return False
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav_file:
                voice.synthesize_wav(self._text, wav_file)

            import winsound

            winsound.PlaySound(buf.getvalue(), winsound.SND_MEMORY)
            return True
        except Exception:
            get_logger().exception("Piper synthesis/playback failed")
            return False

    def _speak_pyttsx3(self):
        try:
            import pyttsx3

            engine = pyttsx3.init()
            hint = config.TTS_FALLBACK_VOICE_HINTS.get(self._lang, "")
            for voice in engine.getProperty("voices"):
                if hint in voice.id.lower():
                    engine.setProperty("voice", voice.id)
                    break
            engine.say(self._text)
            engine.runAndWait()
            del engine
        except Exception:
            get_logger().exception("Offline TTS fallback (pyttsx3) also failed; staying silent")

    async def _synthesize(self) -> Path:
        import edge_tts

        fd, name = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        voice = config.TTS_VOICES.get(self._lang, config.TTS_VOICES[config.DEFAULT_LANGUAGE])
        communicate = edge_tts.Communicate(self._text, voice, rate=config.TTS_RATE)
        await communicate.save(name)
        return Path(name)

    @staticmethod
    def _play_mp3(mp3_path: Path):
        winmm = ctypes.windll.winmm
        alias = "pet_tts_clip"
        winmm.mciSendStringW(f'open "{mp3_path}" type mpegvideo alias {alias}', None, 0, None)
        try:
            winmm.mciSendStringW(f"play {alias} wait", None, 0, None)
        finally:
            winmm.mciSendStringW(f"close {alias}", None, 0, None)
