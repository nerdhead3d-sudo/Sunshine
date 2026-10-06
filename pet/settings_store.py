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
# Re-entrant: save() calls load() while already holding it — a plain Lock
# deadlocked there (the "Impostazioni..." dialog hung the app on OK).
_lock = threading.RLock()

BACKEND_LOCAL = "local"      # offline gpt4all/llama.cpp (pet/local_llm_client.py)
BACKEND_OLLAMA = "ollama"    # local Ollama server (pet/ollama_client.py)
BACKEND_OPENAI = "openai"    # online, user-supplied API key (pet/openai_client.py)
BACKEND_ANTHROPIC = "anthropic"  # online, user-supplied API key (pet/anthropic_client.py)

_DEFAULTS = {
    "chat_backend": BACKEND_LOCAL if config.USE_LOCAL_LLM else BACKEND_OLLAMA,
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "anthropic_api_key": "",
    "anthropic_model": "claude-haiku-4-5",
    # Ollama also has a free hosted "cloud" tier now (ollama.com — `ollama
    # signin` once, then `ollama pull <model>:cloud`), still served through
    # the exact same local Ollama API/client, just a different model name
    # (and optionally a different host, if pointing straight at the cloud
    # endpoint instead of proxying through a local `ollama serve`). Left
    # blank by default = use config.OLLAMA_MODEL/OLLAMA_HOST as before.
    "ollama_model": "",
    "ollama_host": "",
    # "auto" = faster-whisper detects the spoken language on every
    # utterance (the original behavior); anything else pins both
    # listening and replying to that language so a noisy/ambiguous
    # recording can't make Sunshine suddenly switch languages mid-chat —
    # selectable from the tray "Impostazioni..." dialog, applied on top of
    # (and overriding, at each app start) any per-identity language fixed
    # earlier via voice command ("parla in inglese").
    "language": "auto",
    # Pet sound effects (meow, purr, paw thud... pet/overlay/sound_effects.py),
    # toggled from the tray menu.
    "sound_effects": True,
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
