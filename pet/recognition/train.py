"""Shared LBPH training routine for the person/cat models, used both by the
manual enrollment CLI and by the recognizer's automatic learning."""

import json

import cv2
import numpy as np

import config

MODEL_NAMES = {"person": "humans", "cat": "cats"}


def train(kind: str) -> bool:
    """(Re)trains the LBPH model for `kind` from every sample currently on
    disk under RECOGNITION_SAMPLES_DIR/<kind>/<identity>/*.png. Returns False
    if there is nothing to train on."""
    model_name = MODEL_NAMES[kind]
    kind_dir = config.RECOGNITION_SAMPLES_DIR / kind
    identities = sorted(d.name for d in kind_dir.iterdir() if d.is_dir()) if kind_dir.exists() else []
    if not identities:
        return False

    images = []
    labels = []
    label_map = {}
    for label, name in enumerate(identities):
        label_map[label] = name
        for img_path in (kind_dir / name).glob("*.png"):
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                images.append(img)
                labels.append(label)

    if not images:
        return False

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(images, np.array(labels))

    config.RECOGNITION_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    recognizer.save(str(config.RECOGNITION_MODELS_DIR / f"{model_name}.yml"))
    (config.RECOGNITION_MODELS_DIR / f"{model_name}_labels.json").write_text(
        json.dumps(label_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True
