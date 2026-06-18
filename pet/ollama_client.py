"""Thin wrapper around the Ollama chat API with streaming support. Kept as
an alternative backend (set config.USE_LOCAL_LLM = False to use it) behind
the offline local model in pet/local_llm_client.py."""

from collections.abc import Iterator

import ollama

import config
from pet.system_prompt import SYSTEM_PROMPT


class OllamaClient:
    """Builds chat requests and streams replies from Ollama."""

    def __init__(self, model: str = config.OLLAMA_MODEL, host: str = config.OLLAMA_HOST):
        self._client = ollama.Client(host=host)
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
            for chunk in self._client.chat(model=self.model, messages=messages, stream=True):
                piece = chunk["message"]["content"]
                if piece:
                    yield piece
        except Exception as exc:
            yield f"[non riesco a contattare Ollama: {exc}]"
