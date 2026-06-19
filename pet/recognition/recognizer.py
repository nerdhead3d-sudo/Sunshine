"""Webcam-based identity recognition (Haar cascades + LBPH), run off the UI
thread. No manual enrollment is required: unknown faces/cat-faces that stay
in frame for a while are learned automatically and given a placeholder name
("Persona1", "Gatto1", ...), which the rest of the app can later rename to
the person's real name once they say it out loud.
"""

import json
import time

import cv2
import numpy as np

from PySide6.QtCore import QThread, Signal

import config
from pet.logging_setup import get_logger
from pet.recognition.train import MODEL_NAMES, train


class RecognitionService(QThread):
    """Continuously reads the webcam and classifies the most prominent
    face/cat-face against the trained LBPH models. Emits `identity_recognized`
    once a known candidate has been stable for several consecutive frames,
    and `identity_learned` once enough samples of a previously-unknown
    face/cat-face have been collected and auto-trained.
    """

    identity_recognized = Signal(str, str)  # name, kind ("person" | "cat")
    identity_learned = Signal(str, str)     # name, kind
    identity_lost = Signal()
    appearance_changed = Signal(str, str)   # name, region ("capelli" | "barba") — heuristic, see _check_appearance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self._cat_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalcatface_extended.xml"
        )
        self._cascades = {"person": self._face_cascade, "cat": self._cat_cascade}

        self._recognizers = {}
        self._labels = {}
        for kind in ("person", "cat"):
            recognizer, labels = self._load_model(kind)
            self._recognizers[kind] = recognizer
            self._labels[kind] = labels

        self._last_candidate = None
        self._consecutive = 0
        self._currently_identified = None

        self._learn_buffers = {"person": [], "cat": []}
        self._learn_streak = {"person": 0, "cat": 0}

        self._appearance_baselines: dict[str, np.ndarray] = {}
        self._appearance_announced: set[tuple[str, str]] = set()

    @staticmethod
    def _load_model(kind: str):
        model_name = MODEL_NAMES[kind]
        model_path = config.RECOGNITION_MODELS_DIR / f"{model_name}.yml"
        labels_path = config.RECOGNITION_MODELS_DIR / f"{model_name}_labels.json"
        if not model_path.exists() or not labels_path.exists():
            return None, {}

        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(str(model_path))
        labels = {int(k): v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()}
        return recognizer, labels

    def _reload_model(self, kind: str):
        recognizer, labels = self._load_model(kind)
        self._recognizers[kind] = recognizer
        self._labels[kind] = labels

    # -- public API -----------------------------------------------------------

    def stop(self):
        self._running = False

    def rename_identity(self, kind: str, old_name: str, new_name: str):
        """Renames a learned identity on disk and retrains/reloads its model."""
        old_dir = config.RECOGNITION_SAMPLES_DIR / kind / old_name
        new_dir = config.RECOGNITION_SAMPLES_DIR / kind / new_name
        if old_dir.exists() and not new_dir.exists():
            old_dir.rename(new_dir)
        train(kind)
        self._reload_model(kind)
        if self._currently_identified == (old_name, kind):
            self._currently_identified = (new_name, kind)

    # -- main loop --------------------------------------------------------

    def run(self):
        try:
            self._run_loop()
        except Exception:
            get_logger().exception("RecognitionService crashed; webcam recognition is now dead until restart")

    def _run_loop(self):
        self._running = True
        cap = cv2.VideoCapture(config.WEBCAM_INDEX)
        try:
            while self._running:
                if not cap.isOpened():
                    time.sleep(1.0)
                    if self._running:
                        cap.open(config.WEBCAM_INDEX)
                    continue

                ok, frame = cap.read()
                if not ok:
                    self.msleep(500)
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                self._process_frame(gray)

                self.msleep(config.RECOGNITION_INTERVAL_MS)
        finally:
            cap.release()

    def _process_frame(self, gray):
        candidate = None
        for kind in ("person", "cat"):
            roi = self._detect_crop(gray, self._cascades[kind])
            if roi is None:
                self._learn_buffers[kind] = []
                self._learn_streak[kind] = 0
                continue

            recognizer = self._recognizers[kind]
            name = None
            if recognizer is not None:
                label, confidence = recognizer.predict(roi)
                if confidence <= config.RECOGNITION_CONFIDENCE_THRESHOLD and label in self._labels[kind]:
                    name = self._labels[kind][label]

            if name is not None:
                self._learn_buffers[kind] = []
                self._learn_streak[kind] = 0
                if candidate is None:
                    candidate = (name, kind)
                if kind == "person":
                    self._check_appearance(name, roi)
            else:
                self._accumulate_unknown(kind, roi)

        self._update_candidate(candidate)

    @staticmethod
    def _detect_crop(gray, cascade):
        detections = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
        if len(detections) == 0:
            return None
        x, y, w, h = max(detections, key=lambda d: d[2] * d[3])
        return cv2.resize(gray[y : y + h, x : x + w], (200, 200))

    # -- automatic learning -----------------------------------------------

    def _accumulate_unknown(self, kind: str, roi):
        if not config.AUTO_LEARN_ENABLED:
            return

        buffer = self._learn_buffers[kind]
        if buffer and self._frame_diff(buffer[-1], roi) > config.AUTO_LEARN_MAX_FRAME_DIFF:
            # Looks like a different face/cat than the one we were
            # accumulating (e.g. someone else stepped in front of the
            # webcam): restart the buffer instead of mixing the two into
            # one learned identity.
            buffer = []
            self._learn_buffers[kind] = buffer

        buffer.append(roi)
        if len(buffer) >= config.AUTO_LEARN_SAMPLE_COUNT:
            self._commit_learned(kind, buffer)
            self._learn_buffers[kind] = []

    @staticmethod
    def _frame_diff(a, b) -> float:
        return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))

    def _commit_learned(self, kind: str, crops: list):
        name = self._next_auto_name(kind)
        samples_dir = config.RECOGNITION_SAMPLES_DIR / kind / name
        samples_dir.mkdir(parents=True, exist_ok=True)
        for i, crop in enumerate(crops):
            cv2.imwrite(str(samples_dir / f"{i:04d}.png"), crop)

        if train(kind):
            self._reload_model(kind)
            self.identity_learned.emit(name, kind)

    @staticmethod
    def _next_auto_name(kind: str) -> str:
        prefix = "Persona" if kind == "person" else "Gatto"
        kind_dir = config.RECOGNITION_SAMPLES_DIR / kind
        existing = {d.name for d in kind_dir.iterdir() if d.is_dir()} if kind_dir.exists() else set()
        index = 1
        while f"{prefix}{index}" in existing:
            index += 1
        return f"{prefix}{index}"

    # -- appearance change detection (heuristic, pixel-diff based) ----------

    def _check_appearance(self, name: str, roi):
        """Compares the current face crop to the first sample ever saved
        for this identity, region by region (hair/forehead vs. chin), and
        announces once (per region, per run) if either changed enough.
        This is a crude pixel-difference heuristic, not real semantic
        understanding — lighting and angle changes can trigger false
        positives, so thresholds are deliberately conservative."""
        baseline = self._appearance_baselines.get(name)
        if baseline is None:
            baseline = self._load_appearance_baseline(name)
            if baseline is None:
                return
            self._appearance_baselines[name] = baseline

        height = roi.shape[0]
        hair_h = int(height * config.APPEARANCE_HAIR_FRACTION)
        beard_h = int(height * config.APPEARANCE_BEARD_FRACTION)

        hair_diff = self._frame_diff(roi[:hair_h], baseline[:hair_h])
        beard_diff = self._frame_diff(roi[-beard_h:], baseline[-beard_h:])

        if hair_diff > config.APPEARANCE_DIFF_THRESHOLD and (name, "capelli") not in self._appearance_announced:
            self._appearance_announced.add((name, "capelli"))
            self.appearance_changed.emit(name, "capelli")
        elif beard_diff > config.APPEARANCE_DIFF_THRESHOLD and (name, "barba") not in self._appearance_announced:
            self._appearance_announced.add((name, "barba"))
            self.appearance_changed.emit(name, "barba")

    @staticmethod
    def _load_appearance_baseline(name: str):
        sample_dir = config.RECOGNITION_SAMPLES_DIR / "person" / name
        if not sample_dir.exists():
            return None
        files = sorted(sample_dir.glob("*.png"))
        if not files:
            return None
        img = cv2.imread(str(files[0]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        return cv2.resize(img, (200, 200))

    # -- debounced candidate tracking ---------------------------------------

    def _update_candidate(self, candidate):
        if candidate == self._last_candidate:
            self._consecutive += 1
        else:
            self._last_candidate = candidate
            self._consecutive = 1

        if candidate is None:
            if self._currently_identified is not None and self._consecutive >= config.RECOGNITION_CONSECUTIVE_FRAMES:
                self._currently_identified = None
                self.identity_lost.emit()
            return

        if self._consecutive >= config.RECOGNITION_CONSECUTIVE_FRAMES and candidate != self._currently_identified:
            self._currently_identified = candidate
            name, kind = candidate
            self.identity_recognized.emit(name, kind)
