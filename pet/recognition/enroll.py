"""Optional manual enrollment CLI: captures webcam samples for a person or
cat under a chosen name and (re)trains the matching model right away
(face-embedding centroid for people, LBPH for cats — see train.py).

Usage:
    python -m pet.recognition.enroll --identity Marco --kind person
    python -m pet.recognition.enroll --identity Birba --kind cat

This is no longer required for the pet to recognize you: RecognitionService
now learns unknown faces/cat-faces on its own as it sees them repeatedly,
under a placeholder name that gets renamed to the real one once you say it.
Use this CLI only if you want to pre-seed a name instead of waiting for
auto-learning, or to add more samples to an existing identity.

For people, this guides you through a few head poses (Lumo-style guided
enrollment) instead of capturing whatever pose happens to be in frame —
gives the embedding centroid a better spread to match against later.
"""

import argparse
import time

import cv2

import config
from pet.recognition import face_embeddings
from pet.recognition.train import train, train_person

SAMPLES_PER_RUN = 30
FACE_SIZE = (200, 200)

# Guided poses for person enrollment: (instruction shown to the user,
# how many samples to capture in that pose). Varying head angle gives the
# averaged embedding centroid a better spread than 30 near-identical
# frontal shots, closer to how InsightFace itself was trained/evaluated.
PERSON_POSES = [
    ("guarda dritto verso la webcam", 8),
    ("gira leggermente la testa a sinistra", 6),
    ("gira leggermente la testa a destra", 6),
    ("inclina leggermente la testa in alto", 5),
    ("inclina leggermente la testa in basso", 5),
]

CAT_CASCADE_FILE = "haarcascade_frontalcatface_extended.xml"


def capture_samples(identity: str, kind: str) -> int:
    if kind == "person":
        return _capture_samples_person(identity)
    return _capture_samples_cat(identity)


def _capture_samples_person(identity: str) -> int:
    """Guided multi-pose capture using the same InsightFace detector the
    live recognizer uses, on full color frames (better quality than
    cropping the old grayscale Haar samples)."""
    samples_dir = config.RECOGNITION_SAMPLES_DIR / "person" / identity
    samples_dir.mkdir(parents=True, exist_ok=True)
    existing = len(list(samples_dir.glob("*.png")))

    cap = cv2.VideoCapture(config.WEBCAM_INDEX)
    if not cap.isOpened():
        print("Impossibile aprire la webcam.")
        return existing

    captured = 0
    try:
        for instruction, count in PERSON_POSES:
            print(f"\n{instruction} — tra 2 secondi inizio ad acquisire {count} campioni.")
            print("Premi 'q' in qualsiasi momento per interrompere prima.")
            if _countdown(cap, instruction, seconds=2):
                break

            pose_captured = 0
            while pose_captured < count:
                ok, frame = cap.read()
                if not ok:
                    continue

                face = face_embeddings.detect_largest_face(frame)
                if face is not None:
                    x1, y1, x2, y2 = (max(0, int(v)) for v in face.bbox)
                    out_path = samples_dir / f"{existing + captured:04d}.png"
                    cv2.imwrite(str(out_path), frame[y1:y2, x1:x2])
                    captured += 1
                    pose_captured += 1
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                cv2.putText(
                    frame, f"{instruction}: {pose_captured}/{count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
                )
                cv2.imshow("Enrollment - premi q per uscire", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    cap.release()
                    cv2.destroyAllWindows()
                    total = existing + captured
                    print(f"Interrotto. Acquisiti {captured} nuovi campioni (totale per '{identity}': {total}).")
                    return total
    finally:
        cap.release()
        cv2.destroyAllWindows()

    total = existing + captured
    print(f"\nAcquisiti {captured} nuovi campioni (totale per '{identity}': {total}).")
    return total


def _countdown(cap, instruction: str, seconds: int) -> bool:
    """Shows a live preview with a countdown overlay so the user can get
    into position. Returns True if the user pressed 'q' to abort."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        ok, frame = cap.read()
        if ok:
            remaining = max(0, int(deadline - time.time()) + 1)
            cv2.putText(
                frame, f"{instruction} ({remaining})", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2,
            )
            cv2.imshow("Enrollment - premi q per uscire", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return True
    return False


def _capture_samples_cat(identity: str) -> int:
    """Cats still go through the Haar-cascade + grayscale-crop path (LBPH,
    see train.py) — no guided poses, cats don't take instructions."""
    samples_dir = config.RECOGNITION_SAMPLES_DIR / "cat" / identity
    samples_dir.mkdir(parents=True, exist_ok=True)
    existing = len(list(samples_dir.glob("*.png")))

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + CAT_CASCADE_FILE)
    cap = cv2.VideoCapture(config.WEBCAM_INDEX)
    if not cap.isOpened():
        print("Impossibile aprire la webcam.")
        return existing

    print(f"Acquisizione di {SAMPLES_PER_RUN} campioni per '{identity}' (cat).")
    print("Inquadra il muso muovendolo leggermente. Premi 'q' per interrompere prima.")

    captured = 0
    try:
        while captured < SAMPLES_PER_RUN:
            ok, frame = cap.read()
            if not ok:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
            for (x, y, w, h) in detections:
                roi = cv2.resize(gray[y : y + h, x : x + w], FACE_SIZE)
                out_path = samples_dir / f"{existing + captured:04d}.png"
                cv2.imwrite(str(out_path), roi)
                captured += 1
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                break  # one sample per frame, to get varied poses over time

            cv2.putText(
                frame, f"{captured}/{SAMPLES_PER_RUN}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2,
            )
            cv2.imshow("Enrollment - premi q per uscire", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    total = existing + captured
    print(f"Acquisiti {captured} nuovi campioni (totale per '{identity}': {total}).")
    return total


def main():
    parser = argparse.ArgumentParser(description="Acquisisce campioni e addestra il riconoscimento del pet.")
    parser.add_argument("--identity", required=True, help="Nome dell'identità (persona o gatto)")
    parser.add_argument("--kind", required=True, choices=["person", "cat"])
    args = parser.parse_args()

    capture_samples(args.identity, args.kind)
    trained = train_person(args.identity) if args.kind == "person" else train(args.kind)
    if not trained:
        print(f"Nessun campione valido per '{args.kind}', training saltato.")


if __name__ == "__main__":
    main()
