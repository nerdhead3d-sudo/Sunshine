"""Procedurally synthesizes the pet's sound effects (meow, purr, paw thud,
...) as small WAV files, the audio counterpart of generate_placeholders.py:
no recorded/downloaded audio, nothing to license, works offline.

Sounds are kept under ~0.35s on purpose: the voice listener ignores
anything shorter than config.VAD_MIN_SPEECH_SECONDS, so the pet's own
meows coming out of the speakers never get transcribed as something the
user said (there's no echo cancellation in the audio stack). The one
exception, the long falling "miaaaooo", makes SoundEffects pause the
listener for as long as it plays instead.
"""
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
# Bump when a sound's recipe changes, so cached WAVs get regenerated.
VERSION = 2

_rng = np.random.default_rng(7)  # fixed seed: same sounds on every machine


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE


def _envelope(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n)
    a, r = int(SAMPLE_RATE * attack), int(SAMPLE_RATE * release)
    env[:a] = np.linspace(0, 1, a) ** 2
    env[n - r:] *= np.linspace(1, 0, r) ** 2
    return env


def _contour(points: list[tuple[float, float]], n: int) -> np.ndarray:
    """Piecewise-linear curve through (fraction-of-duration, value) points."""
    xs, ys = zip(*points)
    return np.interp(np.linspace(0, 1, n), xs, ys)


def _voice(seconds: float, pitch: list, formants: list, harmonics: int = 14) -> np.ndarray:
    """A crude cat 'voice': harmonic tone following a pitch contour, each
    harmonic weighted by how close it is to the (moving) formant peaks —
    sliding the formants from high to low is what turns a beep into a
    'mi-a-ow'."""
    t = _t(seconds)
    n = len(t)
    f0 = _contour(pitch, n)
    phase = 2 * np.pi * np.cumsum(f0) / SAMPLE_RATE
    peaks = [_contour(f, n) for f in formants]
    out = np.zeros(n)
    for k in range(1, harmonics + 1):
        fk = f0 * k
        weight = sum(np.exp(-((fk - p) / 450.0) ** 2) for p in peaks) + 0.04
        out += weight * np.sin(k * phase) / k ** 0.3
    return out


def meow() -> np.ndarray:
    s = _voice(
        0.34,
        pitch=[(0, 520), (0.35, 780), (1, 430)],
        formants=[[(0, 2600), (0.4, 1500), (1, 900)], [(0, 900), (1, 700)]],
    )
    return s * _envelope(len(s), 0.03, 0.12)


def mew() -> np.ndarray:
    """Short, high, surprised — when grabbed by the mouse."""
    s = _voice(
        0.2,
        pitch=[(0, 820), (0.3, 1050), (1, 900)],
        formants=[[(0, 2800), (1, 1900)], [(0, 1100), (1, 1000)]],
    )
    return s * _envelope(len(s), 0.015, 0.08)


def trill() -> np.ndarray:
    """'Mrrp': rising chirp with a rolled-r flutter — playful pounce."""
    s = _voice(
        0.26,
        pitch=[(0, 380), (1, 640)],
        formants=[[(0, 900), (1, 1800)], [(0, 500), (1, 700)]],
    )
    flutter = 0.55 + 0.45 * np.sin(2 * np.pi * 28 * _t(0.26))
    return s * flutter * _envelope(len(s), 0.02, 0.07)


def purr() -> np.ndarray:
    """Low rumbling purr: band-limited noise pulsed ~26 times a second."""
    t = _t(0.34)
    noise = _rng.standard_normal(len(t))
    kernel = np.hanning(160)  # crude low-pass
    rumble = np.convolve(noise, kernel / kernel.sum(), mode="same")
    pulses = (0.5 + 0.5 * np.sin(2 * np.pi * 26 * t)) ** 3
    tone = np.sin(2 * np.pi * 52 * t) * 0.6
    s = (rumble * 6 + tone) * pulses
    return s * _envelope(len(s), 0.05, 0.12)


def fall_meow() -> np.ndarray:
    """Long 'miaaaooo' while falling: starts high and alarmed, wavers,
    then slides down as the cat drops."""
    seconds = 1.0
    s = _voice(
        seconds,
        pitch=[(0, 700), (0.15, 1000), (0.45, 900), (1, 380)],
        formants=[[(0, 2700), (0.25, 1700), (0.7, 1100), (1, 750)], [(0, 1000), (1, 650)]],
    )
    vibrato = 1 + 0.18 * np.sin(2 * np.pi * 6.5 * _t(seconds))  # wobbly, a bit panicked
    return s * vibrato * _envelope(len(s), 0.04, 0.3)


def hop() -> np.ndarray:
    """Quick upward 'fwip' for the jump onto a window."""
    t = _t(0.16)
    f = np.linspace(260, 720, len(t))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SAMPLE_RATE)
    noise = _rng.standard_normal(len(t))
    breath = np.convolve(noise, np.ones(12) / 12, mode="same")
    s = tone * 0.8 + breath * 0.2
    return s * _envelope(len(s), 0.01, 0.1)


def thud() -> np.ndarray:
    """Soft paw landing: low sine dropping in pitch + a tiny noise tick."""
    t = _t(0.13)
    f = np.linspace(110, 55, len(t))
    body = np.sin(2 * np.pi * np.cumsum(f) / SAMPLE_RATE) * np.exp(-t * 32)
    tick = _rng.standard_normal(len(t)) * np.exp(-t * 300) * 0.25
    return body + tick


SOUNDS = {
    "meow": meow,
    "mew": mew,
    "trill": trill,
    "purr": purr,
    "fall_meow": fall_meow,
    "hop": hop,
    "thud": thud,
}


def _write_wav(path: Path, samples: np.ndarray):
    peak = np.max(np.abs(samples)) or 1.0
    pcm = (samples / peak * 0.85 * 32767).astype(np.int16)  # normalize, leave headroom
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


def generate_all(sounds_dir: Path):
    sounds_dir.mkdir(parents=True, exist_ok=True)
    for name, make in SOUNDS.items():
        _write_wav(sounds_dir / f"{name}.wav", make())
    (sounds_dir / ".version").write_text(str(VERSION), encoding="utf-8")


def ensure(sounds_dir: Path):
    marker = sounds_dir / ".version"
    complete = all((sounds_dir / f"{name}.wav").exists() for name in SOUNDS)
    if complete and marker.exists() and marker.read_text(encoding="utf-8").strip() == str(VERSION):
        return
    generate_all(sounds_dir)


if __name__ == "__main__":
    generate_all(Path(__file__).resolve().parent / "sounds")
