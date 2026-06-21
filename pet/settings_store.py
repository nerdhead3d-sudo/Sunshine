"""User-editable runtime settings (chat backend choice, online API key),
separate from config.py: config.py holds developer-set defaults that ship
with the code, this holds the one thing the user can change live from the
tray menu without touching code or restarting. Persisted as plain JSON
(no need for SQLite here — it's a handful of scalar fields, never queried,
just loaded once and saved on change) in pet/data/settings.json."""

import json
import threading

import config

_SETTINGS_PATH = config.DATA_DIR / "settings.json"
_lock = threading.Lock()

BACKEND_LOCAL = "local"      # offline gpt4all/llama.cpp (pet/local_llm_client.py)
BACKEND_OLLAMA = "ollama"    # local Ollama server (pet/ollama_client.py)
BACKEND_OPENAI = "openai"    # online, user-supplied API key (pet/openai_client.py)

_DEFAULTS = {
    "chat_backend": BACKEND_LOCAL if config.USE_LOCAL_LLM else BACKEND_OLLAMA,
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
}


def load() -> dict:
    with _lock:
        if not _SETTINGS_PATH.exists():
            return dict(_DEFAULTS)
        try:
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return dict(_DEFAULTS)
        merged = dict(_DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in _DEFAULTS})
        return merged


def save(settings: dict):
    with _lock:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        current = load()
        current.update({k: v for k, v in settings.items() if k in _DEFAULTS})
        _SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
