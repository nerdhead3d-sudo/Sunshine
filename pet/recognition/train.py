"""Training routines used by the manual enrollment CLI (pet/recognition/
enroll.py) — RecognitionService trains automatically as it learns, this
is only for pre-seeding a name or adding samples to an existing identity.

Cats: HOG feature centroid (cat_features.py) — recomputes the centroid
descriptor from every saved sample image for that identity. Replaced
LBPH (raw pixel-texture matching): cats have no landmark-based alignment
the way human faces do (just a bounding-box crop), and LBPH's per-pixel
texture comparison is brittle to the pose/tilt differences that come from
not being aligned. HOG describes edge/gradient structure instead, which
holds up much better across pose without needing a downloaded model.
People: deep-learning face embeddings (face_embeddings.py) — recomputes
the centroid embedding from every saved sample image for that identity.
"""

import cv2
import numpy as np

import config
from pet.recognition import cat_features, face_embeddings


def train(kind: str) -> bool:
    """(Re)trains every cat identity's HOG centroid from samples on disk
    under RECOGNITION_SAMPLES_DIR/cat/<identity>/*.png. Returns False if
    there is nothing to train on."""
    kind_dir = config.RECOGNITION_SAMPLES_DIR / kind
    identities = sorted(d.name for d in kind_dir.iterdir() if d.is_dir()) if kind_dir.exists() else []
    if not identities:
        return False

    model_dir = config.RECOGNITION_MODELS_DIR / "cat"
    model_dir.mkdir(parents=True, exist_ok=True)
    trained_any = False
    for name in identities:
        descriptors = []
        for img_path in (kind_dir / name).glob("*.png"):
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                descriptors.append(cat_features.extract(img))
        if not descriptors:
            continue
        centroid = np.stack(descriptors).mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        np.save(model_dir / f"{name}.npy", centroid)
        trained_any = True

    return trained_any


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
