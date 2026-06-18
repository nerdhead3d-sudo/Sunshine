"""Continuous voice-only chat: listens on the microphone, replies via the
configured chat backend, and speaks the answer back — no text UI, just an
always-listening conversational loop. Pausing (e.g. on click) mutes the
microphone without losing the active identity/conversation.

Replies are spoken sentence-by-sentence as they stream in from the model,
instead of waiting for the full response: the pet starts talking after the
first sentence rather than after the whole answer is generated, which cuts
the perceived latency noticeably for longer replies."""

import re
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, QThread, QTimer, Signal

import config
from pet.memory.store import MemoryStore
from pet.mood.classifier import get_classifier
from pet.skills import intents
from pet.voice.stt import ContinuousListener
from pet.voice.tts import SpeakWorker

if config.USE_LOCAL_LLM:
    from pet.local_llm_client import LocalLLMClient as ChatClient
else:
    from pet.ollama_client import OllamaClient as ChatClient

DEFAULT_IDENTITY = "Io"

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = MemoryStore(config.DATA_DIR / "pet_memory.db")
        self._client = ChatClient()

        self._identity_name = ""
        self._identity_id: int | None = None
        self._facts: list[str] = []
        self._conversation: list[dict] = []
        self._pending_user_text = ""

        self._awaiting_name_for: str | None = None
        self._on_named = None

        self._listener = ContinuousListener(self)
        self._listener.utterance_recognized.connect(self._on_utterance)
        self._reply_worker: _ReplyWorker | None = None
        self._reply_buffer = ""
        self._streaming = False

        self._speak_queue: list[str] = []
        self._speaking = False
        self._speak_worker: SpeakWorker | None = None

        self._muted = False
        self._busy = False  # anything in flight (thinking/queued/speaking): listener stays paused

        self.set_identity(DEFAULT_IDENTITY)

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        self._listener.start()
        self._refresh_listening()
        self._reschedule_pending_reminders()

    def stop(self):
        self._listener.stop()

    def set_paused(self, muted: bool):
        self._muted = muted
        self._refresh_listening()

    def _refresh_listening(self):
        if self._muted or self._busy:
            self._listener.pause()
        else:
            self._listener.resume()

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

    def _who_am_i_reply(self) -> str:
        """Answers "chi sono io?"-style questions directly instead of
        relying on the small local model, which tends to ignore the
        identity fact in context and make up silly guesses ("un gatto?",
        "un computer?") for this kind of self-referential question."""
        name = self._identity_name
        if name and name != DEFAULT_IDENTITY and not _PLACEHOLDER_IDENTITY_RE.match(name):
            return f"Sei {name}!"
        return "Non ti ho ancora riconosciuto bene: resta un attimo davanti alla webcam e dovrei capire chi sei."

    def announce(self, text: str):
        """Speaks `text` outside of the normal chat flow (greetings, etc.)."""
        self._enqueue_speech(text)

    def _schedule_announcement(self, seconds: float, text: str):
        """Used by skills (timers/reminders) to speak `text` after a delay.
        Persisted to SQLite so it still fires (immediately, if overdue) even
        if the app is restarted before the delay elapses."""
        due_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        reminder_id = self._store.add_reminder(text, due_at)
        QTimer.singleShot(int(seconds * 1000), lambda: self._fire_reminder(reminder_id, text))

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

    def _on_utterance(self, text: str):
        text = text.strip()
        if not text:
            return

        if self._awaiting_name_for is not None:
            self._handle_name_answer(text)
            return

        if _WHO_AM_I_RE.search(text):
            self.announce(self._who_am_i_reply())
            return

        skill_reply = intents.try_handle(text, self._schedule_announcement)
        if skill_reply is not None:
            self.announce(skill_reply)
            return

        mood_facts = self._update_mood(text)

        self._busy = True
        self._streaming = True
        self._reply_buffer = ""
        self._refresh_listening()

        self._pending_user_text = text
        messages = self._client.build_messages(self._facts + mood_facts, self._conversation, text)
        self._reply_worker = _ReplyWorker(self._client, messages, self)
        self._reply_worker.chunk_ready.connect(self._on_reply_chunk)
        self._reply_worker.finished_reply.connect(self._on_reply_finished)
        self._reply_worker.start()

    def _update_mood(self, text: str) -> list[str]:
        """Classifies `text` with our own from-scratch mood model, nudges
        the identity's running mood score, and returns a transient fact
        (not persisted) so the chat model is aware of the current tone."""
        classifier = get_classifier()
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
        self._speak_queue.append(dialogue)
        self._drain_speak_queue()

    def _drain_speak_queue(self):
        if self._speaking or not self._speak_queue:
            return
        sentence = self._speak_queue.pop(0)
        self._speaking = True
        self._speak_worker = SpeakWorker(sentence, self)
        self._speak_worker.finished_speaking.connect(self._on_sentence_spoken)
        self._speak_worker.start()

    def _on_sentence_spoken(self):
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
