"""Online chat backend via the Anthropic API (Claude), the second online
option next to pet/openai_client.py — both selectable from the tray
"Impostazioni..." dialog so the two can be compared directly against the
local/Ollama backends. Same build_messages/stream_reply interface as
OllamaClient; the only wrinkle is Anthropic's API takes the system prompt
as a separate top-level field instead of a "system" message in the list,
so build_messages keeps it tagged on the first dict entry and stream_reply
pulls it back out."""

from collections.abc import Iterator

from pet.system_prompt import SYSTEM_PROMPT


class AnthropicClient:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
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
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        conversation = [m for m in messages if m["role"] != "system"]
        try:
            with self._client.messages.stream(
                model=self.model, max_tokens=300, system=system, messages=conversation,
            ) as stream:
                yield from stream.text_stream
        except Exception as exc:
            yield f"[non riesco a contattare il servizio online: {exc}]"
