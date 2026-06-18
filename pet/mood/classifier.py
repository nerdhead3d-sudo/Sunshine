"""Inference for the from-scratch mood classifier: loads the weights
trained by pet/mood/train.py and classifies a piece of text into one of
LABELS, with the corresponding numeric valence."""

import threading

import torch

import config
from pet.logging_setup import get_logger
from pet.mood.dataset import LABELS, LABEL_VALENCE
from pet.mood.model import MAX_LEN, MoodNet
from pet.mood.vocab import encode, load_vocab

_classifier = None  # None = not loaded, False = failed to load, else MoodClassifier
_lock = threading.Lock()


class MoodClassifier:
    def __init__(self):
        vocab_path = config.MOOD_MODEL_DIR / "mood_vocab.json"
        weights_path = config.MOOD_MODEL_DIR / "mood_model.pt"
        self._vocab = load_vocab(vocab_path)
        self._model = MoodNet(vocab_size=len(self._vocab), num_classes=len(LABELS))
        self._model.load_state_dict(torch.load(weights_path, weights_only=True))
        self._model.eval()

    def classify(self, text: str) -> tuple[str, float]:
        """Returns (label, valence) for `text`."""
        ids = encode(text, self._vocab, MAX_LEN)
        x = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            logits = self._model(x)
            label = LABELS[int(logits.argmax(dim=1).item())]
        return label, LABEL_VALENCE[label]


def get_classifier() -> "MoodClassifier | None":
    """Lazily loads the trained model once; returns None (logged) if it
    hasn't been trained yet or fails to load, so callers can skip mood
    tracking gracefully instead of crashing."""
    global _classifier
    if _classifier is not None:
        return _classifier or None
    with _lock:
        if _classifier is not None:
            return _classifier or None
        try:
            _classifier = MoodClassifier()
        except Exception:
            get_logger().exception("Mood classifier unavailable (run 'python -m pet.mood.train' first?)")
            _classifier = False
    return _classifier or None
