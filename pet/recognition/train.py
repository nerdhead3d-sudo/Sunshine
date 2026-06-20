"""Training routines used by the manual enrollment CLI (pet/recognition/
enroll.py) — RecognitionService trains automatically as it learns, this
is only for pre-seeding a name or adding samples to an existing identity.

Cats: classical LBPH, retrained from every sample on disk.
People: deep-learning face embeddings (face_embeddings.py) — recomputes
the centroid embedding from every saved sample image for that identity.
"""

import json

import cv2
import numpy as np

import config
from pet.recognition import face_embeddings

MODEL_NAMES = {"cat": "cats"}


def train(kind: str) -> bool:
    """(Re)trains the cat LBPH model from every sample currently on disk
    under RECOGNITION_SAMPLES_DIR/cat/<identity>/*.png. Returns False if
    there is nothing to train on."""
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


def train_person(identity: str) -> bool:
    """Recomputes `identity`'s face-embedding centroid from every sample
    image saved under RECOGNITION_SAMPLES_DIR/person/<identity>/*.png.
    Returns False if no face could be extracted from any sample (e.g. no
    samples yet, or the embedding model failed to load). Samples may be
    color (auto-learning, guided enrollment) or grayscale-replicated
    (older samples) — cv2.imread's default color mode handles both."""
    samples_dir = config.RECOGNITION_SAMPLES_DIR / "person" / identity
    if not samples_dir.exists():
        return False

    embeddings = []
    for img_path in samples_dir.glob("*.png"):
        bgr = cv2.imread(str(img_path))
        if bgr is None:
            continue
        face = face_embeddings.detect_largest_face(bgr)
        if face is not None:
            embeddings.append(face.normed_embedding)

    if not embeddings:
        return False

    centroid = np.stack(embeddings).mean(axis=0)
    centroid = centroid / np.linalg.norm(centroid)

    model_dir = config.RECOGNITION_MODELS_DIR / "person"
    model_dir.mkdir(parents=True, exist_ok=True)
    np.save(model_dir / f"{identity}.npy", centroid)
    return True
