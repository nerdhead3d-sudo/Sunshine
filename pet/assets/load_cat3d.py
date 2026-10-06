"""Turns the pre-rendered 3D cat frames (pet/assets/cat3d/, produced offline
by tools/cat3d/) into the app's <state>/<state>_<index>.png sprites at
config.DISPLAY_SIZE.

The frames already share one crop box with the ground line at the bottom
edge (see tools/cat3d/crop_frames.py), so every frame gets the *same*
scale and placement here — unlike the 2D sheet slicer, nothing is
re-centred per frame and the cat doesn't jitter.
"""
import shutil
from pathlib import Path

from PIL import Image

import config

CAT3D_DIR = Path(__file__).resolve().parent / "cat3d"

# Bump when the frame set or the placement below changes, so
# main.ensure_sprites() regenerates the sprites on disk.
LAYOUT_VERSION = 5

# *_left twins are the mirrored *_right renders (the cat faces right).
_MIRRORED = {"walk_left": "walk_right", "run_left": "run_right"}
# Played backwards: turning back from facing the viewer.
_REVERSED = {"turn_back": "turn_front"}


def available() -> bool:
    return CAT3D_DIR.is_dir() and any(CAT3D_DIR.glob("*/*.png"))


def _frames(state_dir: Path) -> list[Path]:
    return sorted(state_dir.glob("*.png"), key=lambda f: int(f.stem.rsplit("_", 1)[1]))


def generate_all(sprites_dir: Path):
    size = config.DISPLAY_SIZE
    if sprites_dir.exists():
        for old in sprites_dir.iterdir():
            if old.is_dir():
                shutil.rmtree(old)

    rendered = {}
    for state_dir in sorted(p for p in CAT3D_DIR.iterdir() if p.is_dir()):
        state = state_dir.name
        out = sprites_dir / state
        out.mkdir(parents=True, exist_ok=True)
        imgs = []
        for i, f in enumerate(_frames(state_dir)):
            src = Image.open(f).convert("RGBA")
            scale = size / src.width
            scaled = src.resize((size, round(src.height * scale)), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.alpha_composite(scaled, (0, size - scaled.height))  # ground on the bottom edge
            canvas.save(out / f"{state}_{i}.png")
            imgs.append(canvas)
        rendered[state] = imgs

    for left, right in _MIRRORED.items():
        out = sprites_dir / left
        out.mkdir(parents=True, exist_ok=True)
        for i, im in enumerate(rendered.get(right, [])):
            im.transpose(Image.FLIP_LEFT_RIGHT).save(out / f"{left}_{i}.png")
    for name, source in _REVERSED.items():
        out = sprites_dir / name
        out.mkdir(parents=True, exist_ok=True)
        for i, im in enumerate(reversed(rendered.get(source, []))):
            im.save(out / f"{name}_{i}.png")
