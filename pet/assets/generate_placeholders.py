"""Procedurally generates simple pixel-art sprite frames for the desktop pet,
so the app is runnable without any external artwork. Drop real sprite sheets
into pet/assets/sprites/<state>/<state>_<index>.png (same naming) to replace
these placeholders.
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 64
SUPERSAMPLE = 4  # draw this many times larger, then downscale for anti-aliasing
OUTLINE_WIDTH = 3

BODY = (255, 196, 138, 255)         # cream/orange fur
BODY_SHADE = (235, 168, 105, 255)   # darker fur for simple shading
BODY_LIGHT = (255, 235, 214, 255)   # belly/paws
EAR_INNER = (255, 163, 178, 255)    # pink
BLUSH = (255, 178, 188, 255)
DARK = (61, 43, 42, 255)
OUTLINE = (74, 50, 40, 255)
HIGHLIGHT = (255, 255, 255, 255)
WHISKER = (255, 255, 255, 200)


def _canvas():
    return Image.new("RGBA", (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE), (0, 0, 0, 0))


def _s(v):
    """Scales a single coordinate/length up to supersampled space."""
    return v * SUPERSAMPLE


def _inset_triangle(tri, factor):
    cx_ = sum(p[0] for p in tri) / 3
    cy_ = sum(p[1] for p in tri) / 3
    return [(cx_ + (x - cx_) * factor, cy_ + (y - cy_) * factor) for x, y in tri]


def _outset_box(box, amount):
    x0, y0, x1, y1 = box
    return [x0 - amount, y0 - amount, x1 + amount, y1 + amount]


def _frame(bob=0, squash=0, eyes_closed=False, tail_swing=0, ears_flat=False, happy=False):
    img = _canvas()
    draw = ImageDraw.Draw(img)
    ow = _s(OUTLINE_WIDTH)

    body_w = _s(44 + squash)
    body_h = _s(40 - squash)
    cx = _s(SIZE // 2)
    cy = _s(SIZE // 2 + 4 + bob)

    # tail (outline first, then fill, for a crisp stroked look)
    tail_base = (cx + body_w // 2 - _s(6), cy + body_h // 2 - _s(8))
    tail_tip = (tail_base[0] + _s(14 + tail_swing), tail_base[1] - _s(12 + tail_swing // 2))
    draw.line([tail_base, tail_tip], fill=OUTLINE, width=_s(7) + ow)
    draw.line([tail_base, tail_tip], fill=BODY, width=_s(7))
    draw.ellipse(_outset_box([tail_tip[0] - _s(4), tail_tip[1] - _s(4), tail_tip[0] + _s(4), tail_tip[1] + _s(4)], ow // 2), fill=OUTLINE)
    draw.ellipse([tail_tip[0] - _s(4), tail_tip[1] - _s(4), tail_tip[0] + _s(4), tail_tip[1] + _s(4)], fill=BODY)

    # ears (outer)
    ear_h = _s(5 if ears_flat else 14)
    left_ear = [
        (cx - body_w // 2 + _s(2), cy - body_h // 2 + _s(8)),
        (cx - body_w // 2 + _s(10), cy - body_h // 2 - ear_h),
        (cx - body_w // 2 + _s(20), cy - body_h // 2 + _s(6)),
    ]
    right_ear = [
        (cx + body_w // 2 - _s(2), cy - body_h // 2 + _s(8)),
        (cx + body_w // 2 - _s(10), cy - body_h // 2 - ear_h),
        (cx + body_w // 2 - _s(20), cy - body_h // 2 + _s(6)),
    ]
    draw.polygon(left_ear, fill=OUTLINE)
    draw.polygon(right_ear, fill=OUTLINE)
    draw.polygon(_inset_triangle(left_ear, 0.82), fill=BODY)
    draw.polygon(_inset_triangle(right_ear, 0.82), fill=BODY)

    # body (outline behind, fill on top)
    body_box = [cx - body_w // 2, cy - body_h // 2, cx + body_w // 2, cy + body_h // 2]
    draw.ellipse(_outset_box(body_box, ow), fill=OUTLINE)
    draw.ellipse(body_box, fill=BODY)

    # simple shading: a darker crescent along the lower-right of the body
    draw.ellipse([
        cx - body_w * 0.15, cy - body_h * 0.05,
        cx + body_w * 0.52, cy + body_h * 0.52,
    ], fill=BODY_SHADE)
    # cover most of the shading again with the base body color, leaving a sliver
    draw.ellipse([
        cx - body_w * 0.2, cy - body_h * 0.18,
        cx + body_w * 0.46, cy + body_h * 0.46,
    ], fill=BODY)

    # inner ears (on top of body so the visible tip gets a pink patch)
    if not ears_flat:
        draw.polygon(_inset_triangle(left_ear, 0.5), fill=EAR_INNER)
        draw.polygon(_inset_triangle(right_ear, 0.5), fill=EAR_INNER)

    # belly patch
    belly_w = body_w * 0.6
    belly_h = body_h * 0.5
    draw.ellipse([
        cx - belly_w / 2, cy + body_h / 2 - belly_h - _s(2),
        cx + belly_w / 2, cy + body_h / 2 + belly_h / 2,
    ], fill=BODY_LIGHT)

    # paws
    paw_y = cy + body_h // 2 - _s(3)
    draw.ellipse([cx - body_w // 2 + _s(6), paw_y, cx - body_w // 2 + _s(16), paw_y + _s(8)], fill=BODY_LIGHT)
    draw.ellipse([cx + body_w // 2 - _s(16), paw_y, cx + body_w // 2 - _s(6), paw_y + _s(8)], fill=BODY_LIGHT)

    # whiskers
    whisk_y = cy + _s(1)
    for dy in (-_s(3), 0, _s(3)):
        draw.line([(cx - body_w // 2 - _s(2), whisk_y + dy), (cx - body_w // 2 - _s(14), whisk_y + dy * 1.4)], fill=WHISKER, width=max(1, ow // 2))
        draw.line([(cx + body_w // 2 + _s(2), whisk_y + dy), (cx + body_w // 2 + _s(14), whisk_y + dy * 1.4)], fill=WHISKER, width=max(1, ow // 2))

    # eyes
    eye_y = cy - _s(4)
    if eyes_closed:
        draw.arc([cx - _s(13), eye_y - _s(4), cx - _s(3), eye_y + _s(4)], start=180, end=360, fill=DARK, width=_s(3))
        draw.arc([cx + _s(3), eye_y - _s(4), cx + _s(13), eye_y + _s(4)], start=180, end=360, fill=DARK, width=_s(3))
    else:
        draw.ellipse([cx - _s(13), eye_y - _s(5), cx - _s(4), eye_y + _s(6)], fill=DARK)
        draw.ellipse([cx + _s(4), eye_y - _s(5), cx + _s(13), eye_y + _s(6)], fill=DARK)
        draw.ellipse([cx - _s(11), eye_y - _s(4), cx - _s(8), eye_y - _s(1)], fill=HIGHLIGHT)
        draw.ellipse([cx + _s(6), eye_y - _s(4), cx + _s(9), eye_y - _s(1)], fill=HIGHLIGHT)

    # blush
    blush_y = eye_y + _s(6)
    draw.ellipse([cx - _s(18), blush_y, cx - _s(10), blush_y + _s(5)], fill=BLUSH)
    draw.ellipse([cx + _s(10), blush_y, cx + _s(18), blush_y + _s(5)], fill=BLUSH)

    # nose + mouth
    draw.polygon([
        (cx - _s(2), eye_y + _s(5)), (cx + _s(2), eye_y + _s(5)), (cx, eye_y + _s(8)),
    ], fill=BLUSH)
    if happy:
        draw.arc([cx - _s(5), eye_y + _s(6), cx + _s(5), eye_y + _s(14)], start=0, end=180, fill=DARK, width=_s(2))
    else:
        draw.arc([cx - _s(4), eye_y + _s(7), cx, eye_y + _s(11)], start=20, end=160, fill=DARK, width=max(1, ow // 2))
        draw.arc([cx, eye_y + _s(7), cx + _s(4), eye_y + _s(11)], start=20, end=160, fill=DARK, width=max(1, ow // 2))

    return img.resize((SIZE, SIZE), Image.LANCZOS)


_STATE_FRAMES = {
    "idle": [
        dict(bob=0),
        dict(bob=-1),
        dict(bob=0, eyes_closed=True),
        dict(bob=-1),
    ],
    "walk_left": [
        dict(bob=0, tail_swing=4),
        dict(bob=-2, tail_swing=-2, squash=2),
        dict(bob=0, tail_swing=4),
        dict(bob=-2, tail_swing=-2, squash=2),
    ],
    "sit": [
        dict(squash=10),
        dict(squash=10, eyes_closed=True),
    ],
    "react": [
        dict(bob=-4, happy=True),
        dict(bob=-6, happy=True, tail_swing=6),
        dict(bob=-4, happy=True),
        dict(bob=-2, happy=True, tail_swing=-6),
    ],
}


def generate_all(sprites_dir: Path):
    sprites_dir.mkdir(parents=True, exist_ok=True)

    for state, frames in _STATE_FRAMES.items():
        out_dir = sprites_dir / state
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, params in enumerate(frames):
            img = _frame(**params)
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
