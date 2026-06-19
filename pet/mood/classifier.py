"""Inference for the from-scratch mood classifier: loads the weights
trained by pet/mood/train.py and classifies a piece of text into one of
that language's LABELS, with the corresponding numeric valence. One
classifier instance (and cache entry) per language."""

import threading

import torch

import config
from pet.logging_setup import get_logger
from pet.mood.datasets import get_dataset
from pet.mood.model import MAX_LEN, MoodNet
from pet.mood.vocab import encode, load_vocab

_classifiers: dict[str, "MoodClassifier | bool"] = {}  # False = failed to load for that language
_lock = threading.Lock()


class MoodClassifier:
    def __init__(self, lang: str):
        self.lang = lang
        dataset_module = get_dataset(lang)
        self._labels = dataset_module.LABELS
        self._label_valence = dataset_module.LABEL_VALENCE

        model_dir = config.MOOD_MODEL_DIR / lang
        self._vocab = load_vocab(model_dir / "mood_vocab.json")
        self._model = MoodNet(vocab_size=len(self._vocab), num_classes=len(self._labels))
        self._model.load_state_dict(torch.load(model_dir / "mood_model.pt", weights_only=True))
        self._model.eval()

    def classify(self, text: str) -> tuple[str, float]:
        """Returns (label, valence) for `text`."""
        ids = encode(text, self._vocab, MAX_LEN)
        x = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            logits = self._model(x)
            label = self._labels[int(logits.argmax(dim=1).item())]
        return label, self._label_valence[label]


def get_classifier(lang: str = config.DEFAULT_LANGUAGE) -> "MoodClassifier | None":
    """Lazily loads the trained model for `lang` once; returns None
    (logged) if it hasn't been trained yet or fails to load, so callers
    can skip mood tracking gracefully instead of crashing."""
    cached = _classifiers.get(lang)
    if cached is not None:
        return cached or None
    with _lock:
        cached = _classifiers.get(lang)
        if cached is not None:
            return cached or None
        try:
            classifier = MoodClassifier(lang)
        except Exception:
            get_logger().exception(
                "Mood classifier unavailable for '%s' (run 'python -m pet.mood.train --lang %s' first?)", lang, lang
            )
            classifier = False
        _classifiers[lang] = classifier
    return classifier or None
