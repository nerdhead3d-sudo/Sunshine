"""Speech-to-text: a continuously-listening worker using simple energy-based
voice activity detection (no push-to-talk button needed), transcribed
fully offline via faster-whisper (downloads a small Whisper model from
Hugging Face once, then runs on CPU — no internet needed afterwards)."""

import threading

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Signal

import config
from pet.logging_setup import get_logger


class ContinuousListener(QObject):
    """Lives for the whole app session, on a plain threading.Thread rather
    than a QThread: running sounddevice's PortAudio stream inside a QThread
    crashes the process hard (same class of issue as pyttsx3/SAPI5 — see
    tts.py). Auto-calibrates the ambient noise floor once, then repeatedly
    waits for speech, records until a pause, and emits the transcribed text
    — fully hands-free. Use pause()/resume() to mute it (e.g. while the pet
    is talking) without tearing down the audio stream or its thread."""

    utterance_recognized = Signal(str, str)  # text, detected/fixed language code

    BLOCK_SECONDS = 0.1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._paused_event = threading.Event()
        self._whisper = None
        self._fixed_language: str | None = None  # None = auto-detect every utterance

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop_event.set()

    def pause(self):
        self._paused_event.set()

    def resume(self):
        self._paused_event.clear()

    def set_language(self, lang: str | None):
        """Fixes recognition to `lang` (skips auto-detection each time, more
        consistent and a bit faster), or pass None to go back to auto-detect."""
        self._fixed_language = lang

    def _run(self):
        first_failure = True
        while not self._stop_event.is_set():
            try:
                self._run_loop()
                return  # _run_loop only returns normally once stop() was called
            except Exception:
                if first_failure:
                    get_logger().warning(
                        "Voice input unavailable (mic disconnected?); retrying every %ss",
                        config.MIC_RETRY_SECONDS, exc_info=True,
                    )
                    first_failure = False
                self._stop_event.wait(config.MIC_RETRY_SECONDS)

    def _ensure_whisper(self):
        if self._whisper is not None:
            return
        from faster_whisper import WhisperModel

        get_logger().info("Loading local speech-to-text model (first run only)...")
        config.STT_WHISPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self._whisper = WhisperModel(
            config.STT_WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
            download_root=str(config.STT_WHISPER_MODEL_DIR),
        )

    def _run_loop(self):
        self._ensure_whisper()
        blocksize = int(config.STT_SAMPLE_RATE * self.BLOCK_SECONDS)
        with sd.InputStream(samplerate=config.STT_SAMPLE_RATE, channels=1, dtype="int16", blocksize=blocksize) as stream:
            threshold = self._calibrate(stream, blocksize)

            while not self._stop_event.is_set():
                if self._paused_event.is_set():
                    stream.read(blocksize)  # keep draining so the buffer doesn't overflow
                    continue

                recording = self._record_utterance(stream, blocksize, threshold)
                if self._stop_event.is_set():
                    return
                if recording is not None and not self._paused_event.is_set():
                    self._transcribe_and_emit(recording)

    def _calibrate(self, stream, blocksize) -> float:
        levels = []
        blocks = max(1, int(config.VAD_CALIBRATION_SECONDS / self.BLOCK_SECONDS))
        for _ in range(blocks):
            if self._stop_event.is_set():
                break
            data, _ = stream.read(blocksize)
            levels.append(self._rms(data))
        baseline = float(np.mean(levels)) if levels else config.VAD_MIN_THRESHOLD
        return max(baseline * config.VAD_THRESHOLD_MULTIPLIER, config.VAD_MIN_THRESHOLD)

    @staticmethod
    def _rms(data) -> float:
        samples = data.astype(np.float32)
        return float(np.sqrt(np.mean(samples**2)) + 1e-6)

    def _record_utterance(self, stream, blocksize, threshold):
        silence_blocks_needed = max(1, int(config.VAD_SILENCE_SECONDS / self.BLOCK_SECONDS))
        min_speech_blocks = max(1, int(config.VAD_MIN_SPEECH_SECONDS / self.BLOCK_SECONDS))
        start_confirm_blocks = max(1, int(config.VAD_START_CONFIRM_SECONDS / self.BLOCK_SECONDS))

        frames = []
        pending_frames = []   # blocks above threshold not yet confirmed as real speech
        consecutive_above = 0  # to filter out brief clicks/pops/meows as false starts
        speech_blocks = 0
        silence_run = 0
        heard_speech = False

        while not self._stop_event.is_set() and not self._paused_event.is_set():
            data, _ = stream.read(blocksize)
            level = self._rms(data)
            above = level >= threshold

            if not heard_speech:
                if above:
                    consecutive_above += 1
                    pending_frames.append(data.copy())
                    if consecutive_above >= start_confirm_blocks:
                        heard_speech = True
                        frames.extend(pending_frames)
                        pending_frames = []
                        speech_blocks = consecutive_above
                        silence_run = 0
                else:
                    consecutive_above = 0
                    pending_frames = []
            elif above:
                frames.append(data.copy())
                speech_blocks += 1
                silence_run = 0
            else:
                frames.append(data.copy())
                silence_run += 1
                if silence_run >= silence_blocks_needed and speech_blocks >= min_speech_blocks:
                    break

        if not heard_speech or self._stop_event.is_set() or self._paused_event.is_set():
            return None
        return np.concatenate(frames, axis=0)

    def _transcribe_and_emit(self, recording):
        audio = recording.astype(np.float32).flatten() / 32768.0
        text, lang = "", self._fixed_language or config.DEFAULT_LANGUAGE
        try:
            segments, info = self._whisper.transcribe(audio, language=self._fixed_language)
            text = "".join(segment.text for segment in segments).strip()
            lang = info.language if info.language in config.SUPPORTED_LANGUAGES else lang
        except Exception:
            get_logger().exception("Local speech-to-text failed")
        self.utterance_recognized.emit(text, lang)
