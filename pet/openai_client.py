"""Online chat backend via the OpenAI API (or any OpenAI-compatible
endpoint), chosen by the user from the tray "Impostazioni..." dialog
instead of the offline local model/Ollama. Same build_messages/
stream_reply interface as OllamaClient so it's a drop-in replacement —
see pet/overlay/voice_chat.py::_make_client."""

from collections.abc import Iterator

from pet.system_prompt import SYSTEM_PROMPT


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model

    def build_messages(self, facts: list[str], history: list[dict], user_text: str) -> list[dict]:
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
            stream = self._client.chat.completions.create(
                model=self.model, messages=messages, stream=True,
            )
            for chunk in stream:
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        except Exception as exc:
            yield f"[non riesco a contattare il servizio online: {exc}]"
