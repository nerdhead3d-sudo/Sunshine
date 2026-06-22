"""Text-to-speech with a fallback cascade, run off the UI thread:

0. OpenAI TTS (gpt-4o-mini-tts) — only attempted if an OpenAI API key was
   entered in the tray "Impostazioni..." dialog (the same key used for the
   optional OpenAI chat backend). Noticeably more fluid/natural-sounding
   than edge-tts, at the cost of needing that key and a per-call cost.
1. edge-tts (Microsoft Edge's online neural voices) — good quality, free,
   needs internet. The default online tier when no OpenAI key is set.
2. Piper (offline neural voice, ONNX) — good quality, fully local, used
   automatically when there's no internet. The voice model (~60MB per
   language) is downloaded once from Hugging Face on first use.
3. pyttsx3/SAPI5 — offline but robotic, last-resort fallback if Piper
   itself fails to load.

Each tier picks its voice from config.TTS_VOICES / PIPER_VOICE_BASENAMES /
TTS_FALLBACK_VOICE_HINTS based on the requested language. Whichever tier
is used, `finished_speaking` always fires so the rest of the app doesn't
get stuck waiting; failures are logged to pet/data/pet.log.

Synthesis and playback are split (synthesize() / play()) so the caller can
pipeline sentence-by-sentence speech: prepare() synthesizes the *next*
sentence's audio in the background while the *current* one is still
playing, instead of only starting to synthesize after playback finishes —
see VoiceChatController._drain_speak_queue, which is the actual point of
this split. The one exception is the pyttsx3 last-resort tier, which
can't be cleanly pre-synthesized without writing its own audio file
support; it's rare enough in practice (only reached when both OpenAI/
edge-tts and Piper fail) that losing the pipelining benefit there isn't
worth the extra complexity.
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
from pet import settings_store
from pet.logging_setup import get_logger

_OPENAI_TTS_VOICES = {
    "it": "alloy", "en": "alloy", "fr": "alloy",
    "es": "alloy", "de": "alloy", "pt": "alloy",
}  # gpt-4o-mini-tts voices aren't per-language; "alloy" handles all of them well,
   # it follows the input text's language on its own.

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

# A synthesized-but-not-yet-played result: ("mp3", Path) | ("wav", bytes) | ("pyttsx3", None)
SynthResult = tuple[str, object]


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
    """Synthesizes and plays `text` (in `lang`). Synthesis (`synthesize()`)
    and playback (`play()`) are separate steps so a caller can prefetch —
    see `prepare()`/`start()` below and VoiceChatController's speak queue,
    which is the only caller that actually pipelines them."""

    finished_speaking = Signal()

    def __init__(self, text: str, lang: str = config.DEFAULT_LANGUAGE, parent=None):
        super().__init__(parent)
        self._text = clean_for_speech(text)
        self._lang = lang if lang in config.SUPPORTED_LANGUAGES else config.DEFAULT_LANGUAGE
        self._prepared: SynthResult | None = None
        self._prepare_lock = threading.Lock()

    # -- public API -----------------------------------------------------------

    def prepare(self):
        """Synthesizes this sentence's audio right now (blocking) and
        caches it, without playing it. Meant to be called from a
        background thread *while a previous sentence is still playing*,
        so by the time start() runs for this sentence, playback can begin
        immediately instead of waiting for synthesis."""
        with self._prepare_lock:
            if self._prepared is None:
                self._prepared = self.synthesize()

    def start(self):
        """Plays this sentence, synthesizing it first if prepare() wasn't
        already called (or hadn't finished yet) — runs on a background
        thread either way so the caller never blocks."""
        threading.Thread(target=self._run, daemon=True).start()

    def synthesize(self) -> SynthResult:
        """Tries each tier in order, returning as soon as one succeeds:
        OpenAI TTS -> edge-tts -> Piper -> pyttsx3 (which has no real
        "synthesize without playing" step, so it's represented as a
        result that _play() knows to synthesize+play together, later)."""
        result = self._synthesize_openai()
        if result is not None:
            return result
        try:
            mp3_path = asyncio.run(self._synthesize_edge_tts())
            return ("mp3", mp3_path)
        except Exception:
            get_logger().warning(
                "edge-tts failed (likely no internet); trying offline neural voice (Piper)", exc_info=True
            )
        result = self._synthesize_piper()
        if result is not None:
            return result
        get_logger().warning("Piper unavailable; falling back to robotic offline voice (pyttsx3)")
        return ("pyttsx3", None)

    # -- internal: run start()'s background thread -----------------------------

    def _run(self):
        with self._prepare_lock:
            result = self._prepared if self._prepared is not None else self.synthesize()
        self._play(result)
        self.finished_speaking.emit()

    def _play(self, result: SynthResult):
        kind, payload = result
        if kind == "mp3":
            try:
                self._play_mp3(payload)
            finally:
                payload.unlink(missing_ok=True)
        elif kind == "wav":
            import winsound

            winsound.PlaySound(payload, winsound.SND_MEMORY)
        else:  # "pyttsx3": couldn't be pre-synthesized, do it live now
            self._speak_pyttsx3()

    # -- tier 0: OpenAI TTS -----------------------------------------------------

    def _synthesize_openai(self) -> SynthResult | None:
        """Tries the OpenAI TTS voice first if the user entered an API key
        in Impostazioni (same key as the optional OpenAI chat backend, an
        independent choice from it). Returns None — falling through to
        edge-tts — if there's no key, no internet, or the call fails for
        any other reason."""
        api_key = settings_store.load()["openai_api_key"]
        if not api_key:
            return None
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            voice = _OPENAI_TTS_VOICES.get(self._lang, "alloy")
            fd, name = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            mp3_path = Path(name)
            response = client.audio.speech.create(
                model="gpt-4o-mini-tts", voice=voice, input=self._text, response_format="mp3",
            )
            response.write_to_file(mp3_path)
            return ("mp3", mp3_path)
        except Exception:
            get_logger().warning("OpenAI TTS failed; falling back to edge-tts", exc_info=True)
            return None

    # -- tier 1: edge-tts -------------------------------------------------------

    async def _synthesize_edge_tts(self) -> Path:
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

    # -- tier 2: Piper -----------------------------------------------------------

    def _synthesize_piper(self) -> SynthResult | None:
        voice = _get_piper_voice(self._lang)
        if voice is None:
            return None
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav_file:
                voice.synthesize_wav(self._text, wav_file)
            return ("wav", buf.getvalue())
        except Exception:
            get_logger().exception("Piper synthesis failed")
            return None

    # -- tier 3: pyttsx3 (no prefetch — synth and playback happen together) -----

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
