"""Thin wrapper around the Ollama chat API with streaming support. Kept as
an alternative backend (set config.USE_LOCAL_LLM = False to use it) behind
the offline local model in pet/local_llm_client.py."""

from collections.abc import Iterator

import httpx
import ollama

import config
from pet.system_prompt import SYSTEM_PROMPT


def is_reachable(host: str = config.OLLAMA_HOST, timeout: float = 1.5) -> bool:
    """Quick health check (GET /api/version, ~1-2s timeout) used before
    committing to the Ollama backend — without this, a stopped/unreachable
    Ollama server silently turns every chat attempt into a 30-second wait
    followed by a generic error, with no clue why. See
    pet/overlay/voice_chat.py::make_chat_client."""
    try:
        response = httpx.get(f"{host}/api/version", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


class OllamaClient:
    """Builds chat requests and streams replies from Ollama."""

    def __init__(self, model: str = config.OLLAMA_MODEL, host: str = config.OLLAMA_HOST):
        # Explicit timeout: a cloud-routed model (the new "Accedi a Ollama
        # Cloud" option in Impostazioni) goes over the network, and
        # without a timeout a slow/stuck response hangs this client
        # forever — since stream_reply runs in a background QThread, this
        # alone wouldn't freeze the GUI, but it's a real failure mode
        # worth bounding either way instead of waiting indefinitely.
        self._client = ollama.Client(host=host, timeout=30)
        self.model = model

    def build_messages(self, facts: list[str], history: list[dict], user_text: str) -> list[dict]:
        """Assembles the full message list: system prompt (+ known facts about
        the identity), prior conversation history, then the new user message."""
        system = SYSTEM_PROMPT
        if facts:
            facts_text = "\n".join(f"- {fact}" for fact in facts)
            system += f"\n\nCose che sai su questa persona:\n{facts_text}"

        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def stream_reply(self, messages: list[dict]) -> Iterator[str]:
        try:
            for chunk in self._client.chat(
                model=self.model, messages=messages, stream=True,
                options={"temperature": config.OLLAMA_TEMPERATURE},
            ):
                piece = chunk["message"]["content"]
                if piece:
                    yield piece
        except Exception as exc:
            yield f"[non riesco a contattare Ollama: {exc}]"
