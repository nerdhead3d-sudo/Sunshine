"""Registry of per-language mood datasets. Each language module exposes
LABELS, LABEL_VALENCE and EXAMPLES (same shape as pet/mood/datasets/it.py,
our original and most complete dataset). Adding a language means adding a
module here and listing it in LANGUAGE_MODULES — nothing else needs to
change in train.py/classifier.py."""

from importlib import import_module

LANGUAGE_MODULES = {
    "it": "pet.mood.datasets.it",
    "en": "pet.mood.datasets.en",
    "fr": "pet.mood.datasets.fr",
    "es": "pet.mood.datasets.es",
    "de": "pet.mood.datasets.de",
    "pt": "pet.mood.datasets.pt",
}


def get_dataset(lang: str):
    """Returns the (EXAMPLES, LABELS, LABEL_VALENCE) module for `lang`."""
    module_name = LANGUAGE_MODULES.get(lang)
    if module_name is None:
        raise ValueError(f"No mood dataset for language '{lang}'")
    return import_module(module_name)
