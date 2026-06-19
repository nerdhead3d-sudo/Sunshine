"""Derives idle/sit/walk/react sprite frames from two reference photos
(pet/assets/reference/neutro.png, eyes-open neutral pose, and
occhi_chiusi.png, eyes-closed pose) via geometric transforms (zoom, squash,
rotation) instead of asking an image model for a new pose each time. Every
frame is the same source pixels reshaped, so there's no drift in shading,
outline, or art style between frames the way there is when each frame is a
separate AI generation.

Run after replacing the two reference photos:
    python -m pet.assets.generate_from_reference

States that need a genuinely different pose (sleep lying down, dragged
dangling) aren't covered here -- they keep whatever generate_placeholders.py
produced until a dedicated reference photo for that pose exists.
"""

from pathlib import Path

from PIL import Image

SIZE = 64
MARGIN_FRAC = 0.10  # breathing room left around the cropped photo before scaling down

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
NEUTRAL_REF = REFERENCE_DIR / "neutro.png"
EYES_CLOSED_REF = REFERENCE_DIR / "occhi_chiusi.png"


def _load_framed(src: Path) -> Image.Image:
    img = Image.open(src).convert("RGBA")
    img = img.crop(img.getbbox())
    w, h = img.size
    side = max(w, h)
    margin = int(side * MARGIN_FRAC)
    side += margin * 2
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    return canvas


def _transform(base: Image.Image, zoom=1.0, dy=0, squash_x=1.0, squash_y=1.0, rotate=0) -> Image.Image:
    side = base.size[0]
    img = base
    if squash_x != 1.0 or squash_y != 1.0 or zoom != 1.0:
        new_w, new_h = int(side * zoom * squash_x), int(side * zoom * squash_y)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    if rotate:
        img = img.rotate(rotate, resample=Image.BICUBIC, expand=True)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2 + dy), img)
    return canvas.resize((SIZE, SIZE), Image.LANCZOS)


def generate_all(sprites_dir: Path):
    if not NEUTRAL_REF.exists() or not EYES_CLOSED_REF.exists():
        return  # no reference photos yet -- leave the procedural placeholders alone

    neutral = _load_framed(NEUTRAL_REF)
    closed = _load_framed(EYES_CLOSED_REF)

    frames = {
        "idle": [
            _transform(neutral),
            _transform(neutral, zoom=1.02, dy=-2),
            _transform(closed),
            _transform(neutral, zoom=1.02, dy=-2),
        ],
        "sit": [
            _transform(neutral),
            _transform(closed),
        ],
        "walk_left": [
            _transform(neutral, squash_x=0.96, squash_y=1.03, dy=-1),
            _transform(neutral, squash_x=1.04, squash_y=0.96, dy=2),
            _transform(neutral, squash_x=0.96, squash_y=1.03, dy=-1),
            _transform(neutral, squash_x=1.04, squash_y=0.96, dy=2),
        ],
        "react": [
            _transform(neutral, zoom=1.05, dy=-4, rotate=2),
            _transform(neutral, zoom=1.1, dy=-8, rotate=5),
            _transform(neutral, zoom=1.05, dy=-4, rotate=2),
            _transform(neutral, zoom=1.07, dy=-6, rotate=-5),
        ],
    }

    for state, imgs in frames.items():
        out_dir = sprites_dir / state
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(imgs):
            img.save(out_dir / f"{state}_{i}.png")

    # walk_right = mirrored walk_left
    left_dir = sprites_dir / "walk_left"
    right_dir = sprites_dir / "walk_right"
    right_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(left_dir.glob("walk_left_*.png")):
        img = Image.open(f)
        mirrored = img.transpose(Image.FLIP_LEFT_RIGHT)
        idx = f.stem.split("_")[-1]
        mirrored.save(right_dir / f"walk_right_{idx}.png")


if __name__ == "__main__":
    generate_all(Path(__file__).resolve().parent / "sprites")
