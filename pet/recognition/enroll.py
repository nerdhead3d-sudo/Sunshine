"""Optional manual enrollment CLI: captures webcam samples for a person or
cat under a chosen name and (re)trains the matching LBPH model right away.

Usage:
    python -m pet.recognition.enroll --identity Marco --kind person
    python -m pet.recognition.enroll --identity Birba --kind cat

This is no longer required for the pet to recognize you: RecognitionService
now learns unknown faces/cat-faces on its own as it sees them repeatedly,
under a placeholder name that gets renamed to the real one once you say it.
Use this CLI only if you want to pre-seed a name instead of waiting for
auto-learning, or to add more samples to an existing identity.
"""

import argparse

import cv2

import config
from pet.recognition.train import train

SAMPLES_PER_RUN = 30
FACE_SIZE = (200, 200)

_CASCADES = {
    "person": "haarcascade_frontalface_default.xml",
    "cat": "haarcascade_frontalcatface_extended.xml",
}


def _cascade_for(kind: str) -> cv2.CascadeClassifier:
    return cv2.CascadeClassifier(cv2.data.haarcascades + _CASCADES[kind])


def capture_samples(identity: str, kind: str) -> int:
    samples_dir = config.RECOGNITION_SAMPLES_DIR / kind / identity
    samples_dir.mkdir(parents=True, exist_ok=True)
    existing = len(list(samples_dir.glob("*.png")))

    cascade = _cascade_for(kind)
    cap = cv2.VideoCapture(config.WEBCAM_INDEX)
    if not cap.isOpened():
        print("Impossibile aprire la webcam.")
        return existing

    print(f"Acquisizione di {SAMPLES_PER_RUN} campioni per '{identity}' ({kind}).")
    print("Inquadra il volto muovendolo leggermente. Premi 'q' per interrompere prima.")

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
    if not train(args.kind):
        print(f"Nessun campione valido per '{args.kind}', training saltato.")


if __name__ == "__main__":
    main()
