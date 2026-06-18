"""Fully offline, local LLM backend via gpt4all (bundles its own llama.cpp
backend, no compiler/CUDA needed, no separate server process). Replaces the
Ollama dependency: a small quantized GGUF model is downloaded once from
Hugging Face on first use and cached under config.LOCAL_MODEL_DIR.

Exposes the same `build_messages` / `stream_reply` interface as
OllamaClient so it's a drop-in replacement (see VoiceChatController), even
though internally gpt4all is stateful: each identity's conversation lives
in a persistent "chat session" (the model's own KV-cache context) rather
than being replayed from a message list on every call.
"""

import threading
from collections.abc import Iterator

import config
from pet.logging_setup import get_logger
from pet.system_prompt import SYSTEM_PROMPT


class LocalLLMClient:
    def __init__(self):
        self._model = None
        self._init_lock = threading.Lock()
        self._session_cm = None
        self._current_system_prompt = None
        self._turns_in_session = 0

    def build_messages(self, facts: list[str], history: list[dict], user_text: str) -> dict:
        """Unlike OllamaClient, history isn't replayed here — it already
        lives in the model's own context for the current identity/session
        (see _ensure_session). Returns an opaque request for stream_reply."""
        system = SYSTEM_PROMPT
        if facts:
            facts_text = "\n".join(f"- {fact}" for fact in facts)
            system += f"\n\nCose che sai su questa persona:\n{facts_text}"
        return {"system": system, "user_text": user_text}

    def stream_reply(self, request: dict) -> Iterator[str]:
        try:
            self._ensure_model()
            self._ensure_session(request["system"])
            self._turns_in_session += 1
            yield from self._model.generate(
                request["user_text"], max_tokens=config.LOCAL_LLM_MAX_TOKENS, streaming=True
            )
        except Exception as exc:
            get_logger().exception("Local LLM generation failed")
            yield f"[errore del modello locale: {exc}]"

    # -- lazy model loading ---------------------------------------------------

    def _ensure_model(self):
        if self._model is not None:
            return
        with self._init_lock:
            if self._model is not None:
                return
            from gpt4all import GPT4All
            from huggingface_hub import hf_hub_download

            get_logger().info("Downloading/loading local LLM (first run only, ~1 minute)...")
            config.LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            hf_hub_download(
                repo_id=config.LOCAL_LLM_REPO_ID,
                filename=config.LOCAL_LLM_FILENAME,
                local_dir=str(config.LOCAL_MODEL_DIR),
            )
            self._model = GPT4All(
                config.LOCAL_LLM_FILENAME,
                model_path=str(config.LOCAL_MODEL_DIR),
                n_ctx=config.LOCAL_LLM_CONTEXT,
            )

    # -- per-identity chat session --------------------------------------------

    def _ensure_session(self, system_prompt: str):
        needs_reset = (
            self._session_cm is None
            or system_prompt != self._current_system_prompt
            or self._turns_in_session >= config.LOCAL_LLM_MAX_TURNS_PER_SESSION
        )
        if not needs_reset:
            return

        if self._session_cm is not None:
            self._session_cm.__exit__(None, None, None)

        self._current_system_prompt = system_prompt
        self._turns_in_session = 0
        self._session_cm = self._model.chat_session(system_prompt=system_prompt)
        self._session_cm.__enter__()
