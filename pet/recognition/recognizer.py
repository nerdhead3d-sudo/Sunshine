"""Webcam-based identity recognition, run off the UI thread. People are
recognized via deep-learning face embeddings (InsightFace, see
face_embeddings.py); cats stay on Haar cascades + LBPH (InsightFace's
detector/aligner only understands human face geometry). No manual
enrollment is required: unknown faces/cat-faces that stay in frame for a
while are learned automatically and given a placeholder name
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
from pet.recognition import face_embeddings
from pet.recognition.train import MODEL_NAMES, train


class RecognitionService(QThread):
    """Continuously reads the webcam: people are matched against stored
    face embeddings (cosine similarity), cats against a trained LBPH
    model. Emits `identity_recognized` once a known candidate has been
    stable for several consecutive frames, and `identity_learned` once
    enough samples of a previously-unknown face/cat-face have been
    collected and auto-trained.
    """

    identity_recognized = Signal(str, str)  # name, kind ("person" | "cat")
    identity_learned = Signal(str, str)     # name, kind
    identity_lost = Signal()
    appearance_changed = Signal(str, str)   # name, region ("capelli" | "barba") — heuristic, see _check_appearance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

        self._cat_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalcatface_extended.xml"
        )
        self._cat_recognizer, self._cat_labels = self._load_cat_model()

        self._person_embeddings: dict[str, np.ndarray] = self._load_person_embeddings()

        self._last_candidate = None
        self._consecutive = 0
        self._currently_identified = None

        self._cat_learn_buffer: list = []  # list of grayscale crops
        self._person_learn_buffer: list = []  # list of (embedding, grayscale crop) tuples

        self._appearance_baselines: dict[str, np.ndarray] = {}
        self._appearance_announced: set[tuple[str, str]] = set()

    # -- model loading ----------------------------------------------------

    @staticmethod
    def _load_cat_model():
        model_name = MODEL_NAMES["cat"]
        model_path = config.RECOGNITION_MODELS_DIR / f"{model_name}.yml"
        labels_path = config.RECOGNITION_MODELS_DIR / f"{model_name}_labels.json"
        if not model_path.exists() or not labels_path.exists():
            return None, {}

        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(str(model_path))
        labels = {int(k): v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()}
        return recognizer, labels

    def _reload_cat_model(self):
        self._cat_recognizer, self._cat_labels = self._load_cat_model()

    @staticmethod
    def _person_embeddings_dir():
        path = config.RECOGNITION_MODELS_DIR / "person"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_person_embeddings(self) -> dict[str, np.ndarray]:
        embeddings = {}
        for path in self._person_embeddings_dir().glob("*.npy"):
            try:
                embeddings[path.stem] = np.load(path)
            except Exception:
                get_logger().exception("Failed to load face embedding from %s", path)
        return embeddings

    def _save_person_embedding(self, name: str, embedding: np.ndarray):
        np.save(self._person_embeddings_dir() / f"{name}.npy", embedding)
        self._person_embeddings[name] = embedding

    # -- public API -----------------------------------------------------------

    def stop(self):
        self._running = False

    def rename_identity(self, kind: str, old_name: str, new_name: str):
        """Renames a learned identity on disk."""
        old_dir = config.RECOGNITION_SAMPLES_DIR / kind / old_name
        new_dir = config.RECOGNITION_SAMPLES_DIR / kind / new_name
        if old_dir.exists() and not new_dir.exists():
            old_dir.rename(new_dir)

        if kind == "person":
            old_npy = self._person_embeddings_dir() / f"{old_name}.npy"
            if old_npy.exists():
                old_npy.rename(self._person_embeddings_dir() / f"{new_name}.npy")
            embedding = self._person_embeddings.pop(old_name, None)
            if embedding is not None:
                self._person_embeddings[new_name] = embedding
        else:
            train(kind)
            self._reload_cat_model()

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

                self._process_frame(frame)

                self.msleep(config.RECOGNITION_INTERVAL_MS)
        finally:
            cap.release()

    def _process_frame(self, frame):
        person_candidate = self._process_person(frame)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cat_candidate = self._process_cat(gray)

        self._update_candidate(person_candidate or cat_candidate)

    # -- people: deep-learning face embeddings -------------------------------

    def _process_person(self, frame):
        face = face_embeddings.detect_largest_face(frame)
        if face is None:
            self._person_learn_buffer = []
            return None
        embedding = face.normed_embedding
        crop = self._gray_crop_for_baseline(frame, face.bbox)

        name = self._match_person(embedding)
        if name is not None:
            self._person_learn_buffer = []
            if crop is not None:
                self._check_appearance(name, crop)
            return name, "person"

        self._accumulate_unknown_person(embedding, crop)
        return None

    def _match_person(self, embedding: np.ndarray) -> str | None:
        best_name, best_similarity = None, -1.0
        for name, known_embedding in self._person_embeddings.items():
            similarity = face_embeddings.cosine_similarity(embedding, known_embedding)
            if similarity > best_similarity:
                best_name, best_similarity = name, similarity
        if best_similarity >= config.FACE_EMBEDDING_SIMILARITY_THRESHOLD:
            return best_name
        return None

    def _accumulate_unknown_person(self, embedding: np.ndarray, crop):
        if not config.AUTO_LEARN_ENABLED:
            return

        buffer = self._person_learn_buffer
        if buffer:
            similarity = face_embeddings.cosine_similarity(embedding, buffer[-1][0])
            if similarity < config.AUTO_LEARN_MIN_FACE_SIMILARITY:
                # Looks like a different person than the one we were
                # accumulating: restart instead of mixing the two into one
                # learned identity.
                buffer = []

        buffer.append((embedding, crop))
        self._person_learn_buffer = buffer

        if len(buffer) >= config.AUTO_LEARN_SAMPLE_COUNT:
            self._commit_learned_person(buffer)
            self._person_learn_buffer = []

    def _commit_learned_person(self, buffer: list):
        name = self._next_auto_name("person")
        embeddings = np.stack([e for e, _ in buffer])
        centroid = embeddings.mean(axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        self._save_person_embedding(name, centroid)

        samples_dir = config.RECOGNITION_SAMPLES_DIR / "person" / name
        samples_dir.mkdir(parents=True, exist_ok=True)
        for i, (_, crop) in enumerate(buffer):
            if crop is not None:
                cv2.imwrite(str(samples_dir / f"{i:04d}.png"), crop)

        self.identity_learned.emit(name, "person")

    @staticmethod
    def _gray_crop_for_baseline(frame, bbox):
        """A 200x200 grayscale crop of the detected face region, kept only
        for the appearance-change heuristic (_check_appearance), which
        predates the embedding-based pipeline and still works on plain
        crops. Not used for matching."""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = (max(0, int(v)) for v in bbox)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray[y1:y2, x1:x2], (200, 200))

    # -- cats: Haar cascade + LBPH (unchanged) -------------------------------

    def _process_cat(self, gray):
        roi = self._detect_crop(gray, self._cat_cascade)
        if roi is None:
            self._cat_learn_buffer = []
            return None

        name = None
        if self._cat_recognizer is not None:
            label, confidence = self._cat_recognizer.predict(roi)
            if confidence <= config.RECOGNITION_CONFIDENCE_THRESHOLD and label in self._cat_labels:
                name = self._cat_labels[label]

        if name is not None:
            self._cat_learn_buffer = []
            return name, "cat"

        self._accumulate_unknown_cat(roi)
        return None

    @staticmethod
    def _detect_crop(gray, cascade):
        detections = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
        if len(detections) == 0:
            return None
        x, y, w, h = max(detections, key=lambda d: d[2] * d[3])
        return cv2.resize(gray[y : y + h, x : x + w], (200, 200))

    def _accumulate_unknown_cat(self, roi):
        if not config.AUTO_LEARN_ENABLED:
            return

        buffer = self._cat_learn_buffer
        if buffer and self._frame_diff(buffer[-1], roi) > config.AUTO_LEARN_MAX_FRAME_DIFF:
            buffer = []

        buffer.append(roi)
        self._cat_learn_buffer = buffer

        if len(buffer) >= config.AUTO_LEARN_SAMPLE_COUNT:
            self._commit_learned_cat(buffer)
            self._cat_learn_buffer = []

    @staticmethod
    def _frame_diff(a, b) -> float:
        return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))

    def _commit_learned_cat(self, crops: list):
        name = self._next_auto_name("cat")
        samples_dir = config.RECOGNITION_SAMPLES_DIR / "cat" / name
        samples_dir.mkdir(parents=True, exist_ok=True)
        for i, crop in enumerate(crops):
            cv2.imwrite(str(samples_dir / f"{i:04d}.png"), crop)

        if train("cat"):
            self._reload_cat_model()
            self.identity_learned.emit(name, "cat")

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
