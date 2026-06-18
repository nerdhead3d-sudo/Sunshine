"""Shared file logger so background-thread failures that would otherwise
be swallowed silently (TTS, STT, recognition) leave a trace in
pet/data/pet.log instead of disappearing."""

import logging

import config

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("sunshine")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(config.DATA_DIR / "pet.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    _logger = logger
    return _logger
