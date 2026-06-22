"""Deep-learning face recognition for people (InsightFace, ONNX Runtime,
CPU-only) — replaces LBPH for the "person" kind. LBPH compares raw pixel
texture, which is fragile to lighting/pose changes; this instead extracts
a 512-d embedding where the same person's faces cluster together
regardless of lighting/angle/expression, and matches via cosine
similarity. Cats use a separate HOG-based embedding instead (see
cat_features.py/recognizer.py): InsightFace's detector/aligner is built
and trained for human face geometry only.

The model (~15MB, "buffalo_sc" — the small/compact variant, chosen for
compatibility with modest hardware) is downloaded once from InsightFace's
GitHub releases on first use and cached under
config.FACE_EMBEDDING_MODEL_DIR.
"""

import threading

import numpy as np

import config
from pet.logging_setup import get_logger

_app = None  # None = not loaded, False = failed to load, else FaceAnalysis
_lock = threading.Lock()


def _get_app():
    global _app
    if _app is not None:
        return _app or None
    with _lock:
        if _app is not None:
            return _app or None
        try:
            from insightface.app import FaceAnalysis

            config.FACE_EMBEDDING_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            app = FaceAnalysis(name=config.FACE_EMBEDDING_MODEL, root=str(config.FACE_EMBEDDING_MODEL_DIR))
            app.prepare(ctx_id=-1, det_size=config.FACE_EMBEDDING_DET_SIZE)
        except Exception:
            get_logger().exception("Failed to load the face embedding model (InsightFace)")
            app = False
        _app = app
    return app or None


def detect_largest_face(bgr_image):
    """Detects the largest face in a BGR color image and returns the
    insightface `Face` object (with `.normed_embedding` and `.bbox`), or
    None if no face was found or the model isn't available."""
    app = _get_app()
    if app is None:
        return None
    faces = app.get(bgr_image)
    if not faces:
        return None
    return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
