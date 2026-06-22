"""Feature embedding for cats, replacing the raw-pixel LBPH matching that
used to be the only option here. There's no public deep-learning model
for cat-face geometry/embeddings (unlike InsightFace for humans), so this
uses a classical HOG (Histogram of Oriented Gradients) descriptor instead
of LBPH's local binary patterns: LBPH compares raw pixel-level texture
which is brittle to pose (cats aren't aligned by landmarks the way human
faces are — only a bounding-box crop) — HOG describes edge/gradient
*structure*, which holds up much better when the same cat's head is
slightly turned or tilted between frames. No model download needed,
no extra dependency: cv2.HOGDescriptor is part of opencv-contrib already
in requirements.txt.

Same matching shape as pet/recognition/face_embeddings.py: a single
L2-normalized vector per crop, centroid-averaged per identity, matched by
cosine similarity against a threshold (config.CAT_FEATURE_SIMILARITY_THRESHOLD)."""

import cv2
import numpy as np

_WIN_SIZE = (96, 96)
_HOG = cv2.HOGDescriptor(
    _winSize=_WIN_SIZE,
    _blockSize=(32, 32),
    _blockStride=(16, 16),
    _cellSize=(16, 16),
    _nbins=9,
)


def extract(gray_crop: np.ndarray) -> np.ndarray:
    """Returns a unit-length HOG feature vector for a grayscale face crop
    of any size (resized internally to the descriptor's expected window)."""
    resized = cv2.resize(gray_crop, _WIN_SIZE)
    descriptor = _HOG.compute(resized).flatten().astype(np.float32)
    norm = np.linalg.norm(descriptor)
    if norm > 0:
        descriptor = descriptor / norm
    return descriptor


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
