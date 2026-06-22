"""Continuous voice-only chat: listens on the microphone, replies via the
configured chat backend, and speaks the answer back — no text UI, just an
always-listening conversational loop. Pausing (e.g. on click) mutes the
microphone without losing the active identity/conversation.

Replies are spoken sentence-by-sentence as they stream in from the model,
instead of waiting for the full response: the pet starts talking after the
first sentence rather than after the whole answer is generated, which cuts
the perceived latency noticeably for longer replies.

Multi-language: faster-whisper auto-detects the spoken language on every
utterance unless it's been fixed (via a spoken command like "speak
english"/"parla in inglese"), in which case the fixed language is
remembered per identity (pet_memory.db) and reused across restarts. The
PC-skill commands and a few canned replies ("chi sono io?", asking for a
name) are Italian-only for now — unmatched phrases just fall through to
the chat model, which does reply in the active language."""

import re
import threading
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, QThread, QTimer, Signal

import config
from pet import settings_store
from pet.logging_setup import get_logger
from pet.memory.store import MemoryStore
from pet.mood.classifier import get_classifier
from pet.skills import commands, intents, language_commands
from pet.voice.stt import ContinuousListener
from pet.voice.tts import SpeakWorker, stop_playback

DEFAULT_IDENTITY = "Io"


def make_chat_client(settings: dict | None = None) -> tuple[object, str | None]:
    """Builds the chat backend client chosen in settings_store (tray
    "Impostazioni..." dialog): local gpt4all, local Ollama, or one of two
    online backends (OpenAI/Anthropic, user's own API key). Falls back to
    the local backend if an online one is selected but no API key was
    entered yet, or if Ollama was selected but isn't actually reachable
    (see pet.ollama_client.is_reachable — without this check, a stopped
    Ollama server used to silently turn every chat attempt into a
    30-second wait followed by a generic error). Always logs which
    backend/model ended up active. Returns (client, fallback_message):
    the message is None unless a fallback happened, in which case the
    caller (VoiceChatController) speaks it so the user actually finds out
    instead of just getting worse replies with no explanation."""
    settings = settings or settings_store.load()
    backend = settings["chat_backend"]

    if backend == settings_store.BACKEND_OPENAI and settings["openai_api_key"]:
        from pet.openai_client import OpenAIClient

        get_logger().info("Chat backend attivo: OpenAI (modello=%s)", settings["openai_model"])
        return OpenAIClient(settings["openai_api_key"], settings["openai_model"]), None

    if backend == settings_store.BACKEND_ANTHROPIC and settings["anthropic_api_key"]:
        from pet.anthropic_client import AnthropicClient

        get_logger().info("Chat backend attivo: Anthropic (modello=%s)", settings["anthropic_model"])
        return AnthropicClient(settings["anthropic_api_key"], settings["anthropic_model"]), None

    if backend == settings_store.BACKEND_OLLAMA:
        from pet.ollama_client import OllamaClient, is_reachable

        host = settings["ollama_host"] or config.OLLAMA_HOST
        if not is_reachable(host):
            get_logger().warning("Ollama non risponde su %s; uso il modello locale offline", host)
            from pet.local_llm_client import LocalLLMClient

            return LocalLLMClient(), "Ollama non risponde, uso il modello offline per ora."

        # Blank model = config.OLLAMA_MODEL as before; filled in = e.g. a
        # free Ollama Cloud model ("ollama signin" + "ollama pull
        # <model>:cloud"), still served through the same client/API.
        kwargs = {"host": host}
        if settings["ollama_model"]:
            kwargs["model"] = settings["ollama_model"]
        get_logger().info(
            "Chat backend attivo: Ollama (modello=%s, host=%s)",
            settings["ollama_model"] or config.OLLAMA_MODEL, host,
        )
        return OllamaClient(**kwargs), None

    from pet.local_llm_client import LocalLLMClient

    get_logger().info("Chat backend attivo: locale offline (gpt4all)")
    return LocalLLMClient(), None

_SENTENCE_END_RE = re.compile(r"[.!?](?:\s+|$)")
_ACTION_RE = re.compile(r"\*([^*]+)\*")
_WHO_AM_I_RE = re.compile(r"\bchi sono(?: io)?\b|\bsai chi sono\b|\bmi riconosci\b|\bcome mi chiamo\b", re.IGNORECASE)
_PLACEHOLDER_IDENTITY_RE = re.compile(r"^(Persona|Gatto)\d+$")
_NAME_INTRO_PATTERNS = [
    re.compile(r"\bmi chiamo\s+(.+)", re.IGNORECASE),
    re.compile(r"\bil mio nome è\s+(.+)", re.IGNORECASE),
    re.compile(r"\bmi chiamano\s+(.+)", re.IGNORECASE),
    re.compile(r"\bsono\s+(.+)", re.IGNORECASE),
]

_LANGUAGE_DIRECTIVE = {
    "it": "Rispondi sempre in italiano.",
    "en": "Always reply in English.",
    "fr": "Réponds toujours en français.",
    "es": "Responde siempre en español.",
    "de": "Antworte immer auf Deutsch.",
    "pt": "Responde sempre em português.",
}


def _extract_name(spoken: str) -> str:
    """Pulls the actual name out of a self-introduction like "mi chiamo
    Marco" or "sono Marco" instead of naively taking the first word (which
    would wrongly produce "Mi" or "Sono")."""
    text = spoken.strip()
    for pattern in _NAME_INTRO_PATTERNS:
        match = pattern.search(text)
        if match:
            text = match.group(1).strip()
            break
    words = text.split()
    return words[0].capitalize() if words else ""


def _split_actions(text: str) -> tuple[str, list[str]]:
    """Splits out *narrated actions* (e.g. "*si avvicina e ti tocca la
    fronte*") from the actual spoken dialogue, so they can be shown as a
    speech bubble instead of being read aloud."""
    actions = [a.strip() for a in _ACTION_RE.findall(text) if a.strip()]
    dialogue = _ACTION_RE.sub(" ", text)
    dialogue = re.sub(r"\s+", " ", dialogue).strip()
    return dialogue, actions


class _ReplyWorker(QThread):
    """Streams a reply from the chat backend on a background thread,
    forwarding each piece as it arrives plus the accumulated full text once
    finished."""

    chunk_ready = Signal(str)
    finished_reply = Signal()

    def __init__(self, client, messages, parent=None):
        super().__init__(parent)
        self._client = client
        self._messages = messages
        self.full_text = ""

    def run(self):
        parts = []
        for piece in self._client.stream_reply(self._messages):
            parts.append(piece)
            self.chunk_ready.emit(piece)
        self.full_text = "".join(parts)
        self.finished_reply.emit()


class VoiceChatController(QObject):
    """Owns a single, long-lived ContinuousListener plus the listen -> think
    -> speak loop and the active identity's memory (history + facts),
    persisted via MemoryStore. The listener itself is only ever paused or
    resumed, never recreated — recreating/tearing it down per utterance
    raced with its background audio thread and crashed the signal emit."""

    action_ready = Signal(str)  # narrated action text (e.g. "*ti tocca la fronte*"), for the UI to show
    mood_changed = Signal(str, float)  # (label, running valence score) from our own mood classifier
    youtube_requested = Signal(str, str)  # (action: "search"|"play"|"pause"|"close", query) for the UI to handle
    status_changed = Signal(str)  # "listening"|"thinking"|"speaking"|"muted" — see pet/overlay/status_badge.py.
                                   # Exists because the local STT/LLM pipeline is slow enough that without any
                                   # feedback the user can't tell whether Sunshine heard them or is just stuck.

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = MemoryStore(config.DATA_DIR / "pet_memory.db")
        self._client, self._pending_backend_warning = make_chat_client()

        self._identity_name = ""
        self._identity_id: int | None = None
        self._facts: list[str] = []
        self._conversation: list[dict] = []
        self._pending_user_text = ""

        self._fixed_language: str | None = None  # per-identity preference; None = auto-detect
        self._current_language = config.DEFAULT_LANGUAGE  # language of the utterance being handled right now

        self._awaiting_name_for: str | None = None
        self._on_named = None

        self._wake_word_re = re.compile(
            rf"\b{re.escape(config.WAKE_WORD)}\b[,:]?\s*", re.IGNORECASE
        ) if config.WAKE_WORD_ENABLED else None

        self._listener = ContinuousListener(self)
        self._listener.utterance_recognized.connect(self._on_utterance)
        self._reply_worker: _ReplyWorker | None = None
        self._reply_buffer = ""
        self._streaming = False

        self._speak_queue: list[SpeakWorker] = []  # pre-built workers, so the next one can be prepare()'d ahead
        self._speaking = False
        self._speak_worker: SpeakWorker | None = None

        self._muted = False
        self._busy = False  # anything in flight (thinking/queued/speaking): listener stays paused
        self._interrupted = False  # set by interrupt(); stale chunks/replies/speech check this to bail out
        self._last_status = ""

        self.set_identity(DEFAULT_IDENTITY)

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        self.apply_language_setting()
        self._listener.start()
        self._refresh_listening()
        self._reschedule_pending_reminders()
        self._reschedule_active_alarms()
        if self._pending_backend_warning:
            self.announce(self._pending_backend_warning)
            self._pending_backend_warning = None

    def apply_language_setting(self):
        """Applies the tray "Impostazioni..." language choice: "auto" goes
        back to per-utterance detection, anything else pins both listening
        and replying to that language — overrides whatever per-identity
        preference was stored earlier via voice command ("parla in
        inglese"), since the whole point of this setting is "always start
        in this language regardless of what got fixed before"."""
        lang = settings_store.load()["language"]
        self._set_fixed_language(None if lang == "auto" else lang)

    def stop(self):
        self._listener.stop()

    def set_paused(self, muted: bool):
        self._muted = muted
        self._refresh_listening()

    def reload_chat_backend(self):
        """Swaps the active chat client after settings_store changes
        (tray "Impostazioni..." dialog), without restarting the app or
        losing the active identity's conversation history — only the
        backend object itself is replaced."""
        self._client, warning = make_chat_client()
        if warning:
            self.announce(warning)

    def interrupt(self) -> bool:
        """Stops whatever Sunshine is currently thinking/saying (e.g. on
        click). Returns False if it wasn't doing anything, so the caller
        can fall back to its normal click behavior (mute toggle)."""
        if not self._busy:
            return False
        self._interrupted = True
        self._speak_queue.clear()
        self._streaming = False
        stop_playback()
        if self._speak_worker is not None:
            self._speak_worker.deleteLater()
            self._speak_worker = None
        self._speaking = False
        self._busy = False
        self._refresh_listening()
        return True

    def _refresh_listening(self):
        if self._muted or self._busy:
            self._listener.pause()
        else:
            self._listener.resume()
        self._update_status()

    def _update_status(self):
        if self._muted:
            status = "muted"
        elif self._speaking:
            status = "speaking"
        elif self._busy:
            status = "thinking"
        else:
            status = "listening"
        if status != self._last_status:
            self._last_status = status
            self.status_changed.emit(status)

    # -- identity -------------------------------------------------------------

    def set_identity(self, name: str, seen_via_camera: bool = False):
        name = name.strip()
        if not name or name == self._identity_name:
            return
        self._identity_name = name
        self._identity_id = self._store.get_or_create_identity(name)
        self._store.touch_last_seen(self._identity_id)
        self._facts = self._store.get_facts(self._identity_id)
        self._conversation = self._store.get_history(self._identity_id)

        self._fixed_language = self._store.get_language(self._identity_id)
        self._listener.set_language(self._fixed_language)

        if seen_via_camera:
            # In-memory only: tells the model it just recognized this person
            # via the webcam, without polluting the persisted fact list.
            self._facts = self._facts + [f"Hai appena riconosciuto {name} tramite la webcam: è davanti a te."]

    def request_name_for(self, temp_name: str, on_named):
        """Asks the user (currently tracked as `temp_name`) for their real
        name; `on_named(temp_name, real_name)` runs once they answer."""
        self.set_identity(temp_name)
        self._awaiting_name_for = temp_name
        self._on_named = on_named
        self.announce("Ciao! Non so ancora come ti chiami: come ti chiami?")

    def _is_known_identity(self) -> bool:
        """True once webcam recognition has actually put a real name to
        the current speaker — not the unrecognized default profile nor an
        auto-learned-but-not-yet-named placeholder ("Persona1", "Gatto1")."""
        name = self._identity_name
        return bool(name) and name != DEFAULT_IDENTITY and not _PLACEHOLDER_IDENTITY_RE.match(name)

    def _who_am_i_reply(self) -> str:
        """Answers "chi sono io?"-style questions directly instead of
        relying on the small local model, which tends to ignore the
        identity fact in context and make up silly guesses ("un gatto?",
        "un computer?") for this kind of self-referential question."""
        if self._is_known_identity():
            return f"Sei {self._identity_name}!"
        return "Non ti ho ancora riconosciuto bene: resta un attimo davanti alla webcam e dovrei capire chi sei."

    def register_pat(self):
        """Nudges the current identity's mood positively — petting the pet
        (Lumo-style "carezza") is a small affectionate interaction, separate
        from anything said in chat."""
        if self._identity_id is None:
            return
        new_mood = self._store.update_mood(self._identity_id, config.PET_STROKE_MOOD_VALENCE, config.MOOD_EMA_ALPHA)
        self.mood_changed.emit("carezza", new_mood)

    def greet(self, name: str):
        """Speaks a greeting for `name`, upgraded to a short morning/evening
        routine (Lumo-style) the first time they're recognized in that
        period of the day: time, date, and a nudge about any pending
        reminders. Falls back to a plain "Ciao!" the rest of the time."""
        period = self._current_routine_period()
        if period is None or self._identity_id is None:
            self.announce(f"Ciao {name}!")
            return

        marker = f"{datetime.now().date().isoformat()}:{period}"
        if self._store.get_last_routine(self._identity_id) == marker:
            self.announce(f"Ciao {name}!")
            return

        self._store.set_last_routine(self._identity_id, marker)
        self.announce(self._routine_phrase(name, period))

    @staticmethod
    def _current_routine_period() -> str | None:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "mattina"
        if 18 <= hour < 24:
            return "sera"
        return None

    def _routine_phrase(self, name: str, period: str) -> str:
        time_str = commands.current_time()
        pending = len(self._store.get_pending_reminders())
        if period == "mattina":
            phrase = f"Buongiorno {name}! Sono le {time_str}, oggi è {commands.current_date()}."
        else:
            phrase = f"Buonasera {name}! Sono le {time_str}."
        if pending:
            phrase += f" Hai ancora {pending} promemoria in sospeso."
        return phrase

    def announce(self, text: str):
        """Speaks `text` outside of the normal chat flow (greetings, etc.),
        in the currently active language."""
        self._enqueue_speech(text)

    def _schedule_announcement(self, seconds: float, text: str):
        """Used by skills (timers/reminders) to speak `text` after a delay.
        Persisted to SQLite so it still fires (immediately, if overdue) even
        if the app is restarted before the delay elapses."""
        due_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        reminder_id = self._store.add_reminder(text, due_at)
        QTimer.singleShot(int(seconds * 1000), lambda: self._fire_reminder(reminder_id, text))

    def _schedule_alarm(self, hour: int, minute: int, recurring: bool):
        """Called from intents.try_handle on "svegliami alle X" /
        "tutti i giorni alle X". Persisted to SQLite (alarms table) so
        recurring alarms keep firing across restarts."""
        message = "Sveglia!"
        alarm_id = self._store.add_alarm(hour, minute, recurring, message)
        self._schedule_next_alarm_fire(alarm_id, hour, minute, recurring, message)

    def _schedule_next_alarm_fire(self, alarm_id: int, hour: int, minute: int, recurring: bool, message: str):
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        delay_seconds = (target - now).total_seconds()
        QTimer.singleShot(
            int(delay_seconds * 1000),
            lambda: self._fire_alarm(alarm_id, hour, minute, recurring, message),
        )

    def _fire_alarm(self, alarm_id: int, hour: int, minute: int, recurring: bool, message: str):
        self._store.mark_alarm_fired(alarm_id, datetime.now().date().isoformat())
        self._play_alarm_sound()
        self.announce(message)
        if recurring:
            self._schedule_next_alarm_fire(alarm_id, hour, minute, recurring, message)
        else:
            self._store.disable_alarm(alarm_id)

    @staticmethod
    def _play_alarm_sound():
        def _beep():
            try:
                import winsound
                for _ in range(3):
                    winsound.Beep(880, 200)
            except Exception:
                pass
        threading.Thread(target=_beep, daemon=True).start()

    def _reschedule_active_alarms(self):
        """Re-arms every still-enabled alarm on startup: recurring ones
        always, one-shot ones too (in case the app was closed before they
        fired) — unless one already fired today (e.g. the app restarted a
        few seconds after a recurring alarm went off)."""
        today_str = datetime.now().date().isoformat()
        for alarm in self._store.get_active_alarms():
            if alarm["last_fired_date"] == today_str:
                continue
            self._schedule_next_alarm_fire(
                alarm["id"], alarm["hour"], alarm["minute"], alarm["recurring"], alarm["message"],
            )

    def _reschedule_pending_reminders(self):
        now = datetime.now(timezone.utc)
        for reminder in self._store.get_pending_reminders():
            due_at = datetime.fromisoformat(reminder["due_at"])
            delay_seconds = max(0.0, (due_at - now).total_seconds())
            QTimer.singleShot(
                int(delay_seconds * 1000),
                lambda rid=reminder["id"], msg=reminder["message"]: self._fire_reminder(rid, msg),
            )

    def _fire_reminder(self, reminder_id: int, text: str):
        self._store.mark_reminder_fired(reminder_id)
        self.announce(text)

    # -- listening loop -----------------------------------------------------

    def _on_utterance(self, text: str, detected_lang: str):
        text = text.strip()
        if not text:
            return

        self._interrupted = False

        if self._awaiting_name_for is not None:
            self._handle_name_answer(text)
            return

        if self._wake_word_re is not None:
            match = self._wake_word_re.search(text)
            if match is None:
                return  # wake word not heard: ignore, stay silently listening
            text = (text[: match.start()] + text[match.end() :]).strip()
            if not text:
                self.announce("Sì?")
                return

        is_lang_command, target_lang = language_commands.detect(text)
        if is_lang_command:
            self._set_fixed_language(target_lang)
            self.announce(language_commands.confirmation_for(target_lang))
            return

        self._current_language = self._fixed_language or detected_lang

        if _WHO_AM_I_RE.search(text):
            self.announce(self._who_am_i_reply())
            return

        skill_reply = intents.try_handle(
            text, self._schedule_announcement,
            allow_open_apps=self._is_known_identity(),
            schedule_alarm=self._schedule_alarm,
            youtube_action=lambda action, query: self.youtube_requested.emit(action, query),
        )
        if skill_reply is not None:
            self.announce(skill_reply)
            return

        mood_facts = self._update_mood(text)
        directive = _LANGUAGE_DIRECTIVE.get(self._current_language, _LANGUAGE_DIRECTIVE["it"])

        self._busy = True
        self._streaming = True
        self._reply_buffer = ""
        self._refresh_listening()

        self._pending_user_text = text
        messages = self._client.build_messages([directive] + self._facts + mood_facts, self._conversation, text)
        self._reply_worker = _ReplyWorker(self._client, messages, self)
        self._reply_worker.chunk_ready.connect(self._on_reply_chunk)
        self._reply_worker.finished_reply.connect(self._on_reply_finished)
        self._reply_worker.start()

    def _set_fixed_language(self, lang: str | None):
        self._fixed_language = lang
        self._current_language = lang or self._current_language
        self._listener.set_language(lang)
        if self._identity_id is not None:
            self._store.set_language(self._identity_id, lang)

    def _update_mood(self, text: str) -> list[str]:
        """Classifies `text` with our own from-scratch mood model (one per
        language), nudges the identity's running mood score, and returns a
        transient fact (not persisted) so the chat model is aware of the
        current tone."""
        classifier = get_classifier(self._current_language)
        if classifier is None or self._identity_id is None:
            return []

        label, valence = classifier.classify(text)
        new_mood = self._store.update_mood(self._identity_id, valence, config.MOOD_EMA_ALPHA)
        self.mood_changed.emit(label, new_mood)
        return [f"Il tono attuale di {self._identity_name} sembra: {label}."]

    def _handle_name_answer(self, spoken_name: str):
        temp_name = self._awaiting_name_for
        callback = self._on_named
        self._awaiting_name_for = None
        self._on_named = None

        real_name = _extract_name(spoken_name) or temp_name

        self._store.rename_identity(temp_name, real_name)
        self._identity_name = real_name
        if callback:
            callback(temp_name, real_name)

        self.announce(f"Piacere, {real_name}!")

    # -- streaming reply -> sentence-by-sentence speech ----------------------

    def _on_reply_chunk(self, piece: str):
        if self._interrupted:
            return
        self._reply_buffer += piece
        while True:
            match = _SENTENCE_END_RE.search(self._reply_buffer)
            if not match:
                break
            sentence = self._reply_buffer[: match.end()].strip()
            self._reply_buffer = self._reply_buffer[match.end() :]
            if sentence:
                self._enqueue_speech(sentence)

    def _on_reply_finished(self):
        self._streaming = False
        reply_text = self._reply_worker.full_text if self._reply_worker else ""
        if self._reply_worker is not None:
            self._reply_worker.deleteLater()
            self._reply_worker = None

        if self._interrupted:
            self._reply_buffer = ""
            return

        leftover = self._reply_buffer.strip()
        self._reply_buffer = ""
        if leftover:
            self._enqueue_speech(leftover)

        if self._identity_id is not None:
            self._store.add_message(self._identity_id, "user", self._pending_user_text)
            self._store.add_message(self._identity_id, "assistant", reply_text)
        self._conversation.append({"role": "user", "content": self._pending_user_text})
        self._conversation.append({"role": "assistant", "content": reply_text})

        self._maybe_clear_busy()

    # -- speech queue ---------------------------------------------------------

    def _enqueue_speech(self, text: str):
        text = text.strip()
        if not text:
            return

        dialogue, actions = _split_actions(text)
        for action in actions:
            self.action_ready.emit(action)

        if not dialogue:
            return

        self._busy = True
        self._refresh_listening()
        worker = SpeakWorker(dialogue, self._current_language, self)
        self._speak_queue.append(worker)
        if self._speaking:
            # Already mid-sentence: this new one will just sit in the
            # queue for a while, so start preparing its audio now instead
            # of waiting until it's popped (see _drain_speak_queue, which
            # covers the case where the queue was empty a moment ago).
            self._maybe_prefetch_next()
        self._drain_speak_queue()

    def _drain_speak_queue(self):
        if self._speaking or not self._speak_queue:
            return
        worker = self._speak_queue.pop(0)
        self._speaking = True
        self._update_status()
        self._speak_worker = worker
        worker.finished_speaking.connect(self._on_sentence_spoken)
        worker.start()
        self._maybe_prefetch_next()

    def _maybe_prefetch_next(self):
        """Starts synthesizing the next queued sentence's audio on a
        background thread right away, instead of waiting until the
        current one finishes playing — cuts the dead air between
        sentences on longer replies. SpeakWorker.prepare() is itself
        idempotent/lock-guarded, so calling this more than once for the
        same head-of-queue worker is harmless."""
        if self._speak_queue:
            threading.Thread(target=self._speak_queue[0].prepare, daemon=True).start()

    def _on_sentence_spoken(self):
        if not self._speaking:
            return  # stale signal from a worker interrupt() already cleaned up
        if self._speak_worker is not None:
            self._speak_worker.deleteLater()
            self._speak_worker = None
        self._speaking = False
        self._drain_speak_queue()
        self._maybe_clear_busy()

    def _maybe_clear_busy(self):
        if not self._streaming and not self._speaking and not self._speak_queue:
            self._busy = False
            self._refresh_listening()
