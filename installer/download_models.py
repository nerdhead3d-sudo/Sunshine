"""Run by the installer (Inno Setup [Run] step) right after files are
copied, so the multi-hundred-MB model downloads happen during setup with
visible progress instead of silently on Sunshine's first launch (which
otherwise looks like the app is frozen for a few minutes).

Usage: Sunshine.exe's own Python runtime isn't available yet as a
separate interpreter once frozen, so this script is meant to run from the
*installer's bundled venv copy* during the build step before packaging,
OR — more simply, the approach actually wired into setup.iss — by
invoking the frozen Sunshine.exe itself with a hidden "--download-models"
flag (see main.py), so it reuses the exact same frozen Python/torch/etc.
without needing a second interpreter inside the installer.

Kept here as a standalone module, imported by main.py's "--download-models"
flag handler, so the download logic isn't duplicated between "normal first
run" (each module downloads its own model lazily on first use) and
"installer-triggered early download" (this script, called once up front).
"""

import subprocess
import sys

import config


def download_whisper():
    from faster_whisper import WhisperModel

    print(f"Scarico il modello Whisper ({config.STT_WHISPER_MODEL})...")
    config.STT_WHISPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    WhisperModel(
        config.STT_WHISPER_MODEL, device="cpu", compute_type="int8",
        download_root=str(config.STT_WHISPER_MODEL_DIR),
    )
    print("Whisper pronto.")


def download_piper(lang: str = config.DEFAULT_LANGUAGE):
    from huggingface_hub import hf_hub_download

    print(f"Scarico la voce offline Piper per '{lang}'...")
    config.PIPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    base = config.PIPER_VOICE_BASENAMES[lang]
    for suffix in (".onnx", ".onnx.json"):
        hf_hub_download(
            repo_id=config.PIPER_VOICE_REPO, filename=f"{base}{suffix}",
            local_dir=str(config.PIPER_MODEL_DIR),
        )
    print("Voce Piper pronta.")


def download_local_llm():
    if not config.USE_LOCAL_LLM:
        return
    from huggingface_hub import hf_hub_download

    print("Scarico il modello di chat offline (gpt4all)...")
    config.LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    hf_hub_download(
        repo_id=config.LOCAL_LLM_REPO_ID, filename=config.LOCAL_LLM_FILENAME,
        local_dir=str(config.LOCAL_MODEL_DIR),
    )
    print("Modello di chat offline pronto.")


def pull_ollama_model():
    """Best-effort: if Ollama is installed, pre-pull config.OLLAMA_MODEL so
    it's cached before first use. Silently skipped if Ollama isn't on the
    PATH — the installer's Ollama-check page already warned the user about
    that separately, no need to fail the whole download step over it."""
    try:
        subprocess.run(
            ["ollama", "pull", config.OLLAMA_MODEL],
            timeout=600, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("Ollama non trovato o non risponde: salto il pre-download del modello Ollama.")


def main(lang: str = config.DEFAULT_LANGUAGE):
    download_whisper()
    download_piper(lang)
    download_local_llm()
    pull_ollama_model()
    print("Download completato.")


if __name__ == "__main__":
    main()
