"""Second step after render_cat_3d.py: crops every rendered frame with ONE
shared box (union of all frames horizontally and at the top, the ground
line at the bottom) and saves them into pet/assets/cat3d/<state>/.

A single box for all frames — instead of cropping each frame to its own
bounds like the 2D sprite-sheet slicer has to — keeps the camera fixed: the
cat never jitters sideways between frames and keeps the same size across
states. Paw tips dipping a few pixels below the ground line get clipped,
which reads as paws planted on the floor.

Usage (from the repo root, with the project venv):
  python tools/cat3d/crop_frames.py <rendered_dir>
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Must match the camera in render_cat_3d.py.
RENDER_SIZE = 640
CAM_Z = 0.15
ORTHO_SCALE = 2.6
GROUND_Z = -0.69

OUT_WIDTH = 400  # stored size; the app rescales to config.DISPLAY_SIZE
DEST = Path(__file__).resolve().parents[2] / "pet" / "assets" / "cat3d"


def main(src: Path):
    files = sorted(src.glob("*/*.png"))
    ground_row = round(RENDER_SIZE * (0.5 + (CAM_Z - GROUND_Z) / ORTHO_SCALE))
    x0, x1, top = RENDER_SIZE, 0, RENDER_SIZE
    for f in files:
        alpha = np.asarray(Image.open(f))[..., 3]
        ys, xs = np.nonzero(alpha > 8)
        x0, x1, top = min(x0, xs.min()), max(x1, xs.max()), min(top, ys.min())
    box = (x0, top, x1 + 1, ground_row)
    scale = OUT_WIDTH / (box[2] - box[0])
    size = (OUT_WIDTH, round((box[3] - box[1]) * scale))
    print(f"{len(files)} frames, box {box}, stored at {size}")

    for f in files:
        state = f.parent.name
        (DEST / state).mkdir(parents=True, exist_ok=True)
        Image.open(f).crop(box).resize(size, Image.LANCZOS).save(DEST / state / f.name, optimize=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
