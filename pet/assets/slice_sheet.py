"""Cuts the black-cat sprite sheet (pet/assets/sheets/black_cat.png, RGBA
with a real transparent background) into per-state frame PNGs, in the same
<state>/<state>_<index>.png layout the placeholder generator writes.

Layout of the sheet: one animation per row, a text label on the far left
(IDLE, WALK, RUN, ...), frames left to right. Each opaque blob right of the
label column is one frame; the labels themselves are only used to find the
vertical centre of each row, so a regenerated sheet with slightly different
spacing still slices correctly as long as the row order stays the same.
"""
import shutil
from pathlib import Path

import cv2
import numpy as np

import config

SHEET_PATH = Path(__file__).resolve().parent / "sheets" / "black_cat.png"

# Row order on the sheet, top to bottom.
_ROW_NAMES = ["IDLE", "WALK", "RUN", "JUMP", "FALL", "LAND", "ATTACK", "HURT", "DIE", "SLEEP"]
_LABEL_COLUMN_WIDTH = 110   # left strip holding the row labels, not cats
_MIN_BLOB_AREA = 1500       # smaller blobs are stray whiskers/noise, not frames

# App state -> (sheet row, frame indices or None for all). The sheet faces
# right: *_right states are taken as-is, their *_left twin is mirrored (see
# _MIRRORED); every other state is mirrored at runtime by SpriteAnimator.
_STATE_SOURCES = {
    "idle": ("IDLE", list(range(9))),     # last IDLE frame is already seated: would pop in the loop
    "walk_right": ("WALK", None),
    "run_right": ("RUN", None),
    "sit": ("HURT", [4, 5, 6, 7]),        # seated, eyes closed/half closed
    "react": ("JUMP", [0, 1, 7, 8]),      # crouch + little hop, back on the ground
    "sleep": ("SLEEP", [1, 6]),           # the row is a lying-down sequence; keep only curled-up poses
    "dragged": ("FALL", [1, 2, 3]),       # curled up, paws in the air
    "jump": ("JUMP", None),               # one-shot, jumping onto a window
    "fall": ("FALL", [4, 5, 6, 7]),       # legs reaching down, looped while falling
    "land": ("LAND", None),               # one-shot touchdown
    "play": ("ATTACK", None),             # one-shot playful pounce
}
_MIRRORED = {"walk_left": "walk_right", "run_left": "run_right"}
# Rows the state machine doesn't use (yet): sliced too, so a new state can
# pick them up without touching this module again.
_EXTRA_ROWS = ["HURT", "DIE"]

# Bump when the row -> state mapping above changes: main.ensure_sprites()
# re-slices when this differs from what's recorded next to the sprites.
LAYOUT_VERSION = 2

# Square output, sliced straight at the on-screen size so SpriteAnimator
# doesn't resample a second time.
FRAME_SIZE = config.DISPLAY_SIZE


def _row_labels(alpha: np.ndarray) -> tuple[dict[str, float], list[tuple[int, int, int, int]]]:
    """Returns ({row name: vertical centre}, [label box (x, y, w, h), ...])."""
    labels_mask = (alpha[:, :_LABEL_COLUMN_WIDTH] > 128).astype(np.uint8)
    n, _, stats, centroids = cv2.connectedComponentsWithStats(labels_mask)
    # Labels are wide, short rounded boxes; anything else here is a tail tip
    # poking into the label column.
    found = sorted(
        (centroids[i][1], tuple(int(v) for v in stats[i][:4])) for i in range(1, n)
        if stats[i][2] > 50 and stats[i][3] < stats[i][2] * 0.6
    )
    if len(found) != len(_ROW_NAMES):
        raise ValueError(f"expected {len(_ROW_NAMES)} row labels on the sprite sheet, found {len(found)}")
    return dict(zip(_ROW_NAMES, (y for y, _ in found))), [box for _, box in found]


def _blobs_by_row(alpha: np.ndarray):
    mask = (alpha > 128).astype(np.uint8)
    mask[:, :_LABEL_COLUMN_WIDTH] = 0
    # A light erosion splits neighbouring frames that touch by a whisker or
    # a paw tip; each frame later takes back its full soft edge from `alpha`.
    core = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(core, connectivity=8)

    centres, label_boxes = _row_labels(alpha)
    rows = {name: [] for name in _ROW_NAMES}
    for i in range(1, n):
        if stats[i][4] < _MIN_BLOB_AREA:
            continue
        row = min(centres, key=lambda r: abs(centres[r] - centroids[i][1]))
        rows[row].append(i)
    for ids in rows.values():
        ids.sort(key=lambda i: stats[i][0])

    # Give every non-transparent pixel back to its nearest core blob, so the
    # soft anti-aliased edge (and whiskers) the erosion removed come back.
    keep = np.isin(labels, [i for ids in rows.values() for i in ids])
    _, nearest = cv2.distanceTransformWithLabels(
        (~keep).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )
    seed_label = np.zeros(nearest.max() + 1, np.int32)
    seed_label[nearest[keep]] = labels[keep]
    owner = seed_label[nearest]
    owner[alpha == 0] = 0
    # A label's soft edge can touch the first frame of its row: never let
    # label pixels be handed to a cat.
    for x, y, w, h in label_boxes:
        owner[max(0, y - 3):y + h + 3, max(0, x - 3):x + w + 3] = 0
    return rows, owner


def slice_frames() -> dict[str, list[np.ndarray]]:
    """Returns {sheet row name: [BGRA frame, ...]}, every frame at the same
    scale with the cat's lowest pixel on the bottom edge, so it doesn't
    jump around or change size between frames and states."""
    img = cv2.imread(str(SHEET_PATH), cv2.IMREAD_UNCHANGED)
    if img is None or img.ndim != 3 or img.shape[2] != 4:
        raise ValueError(f"{SHEET_PATH} must be an RGBA PNG with a transparent background")
    # The sheet has a near-invisible haze (alpha < 16) around every cat. Left
    # in, it inflates each frame's bounding box — the cat floats ~10px above
    # the taskbar and is scaled smaller than it needs to be.
    img[:, :, 3][img[:, :, 3] < 16] = 0
    rows, owner = _blobs_by_row(img[:, :, 3])

    boxes = {}
    for ids in rows.values():
        for i in ids:
            ys, xs = np.nonzero(owner == i)
            boxes[i] = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    biggest = max(max(x1 - x0, y1 - y0) for x0, y0, x1, y1 in boxes.values())
    scale = (FRAME_SIZE * 0.96) / biggest

    out = {}
    for row, ids in rows.items():
        frames = []
        for i in ids:
            x0, y0, x1, y1 = boxes[i]
            crop = img[y0:y1, x0:x1].copy()
            crop[owner[y0:y1, x0:x1] != i, 3] = 0  # drop bits of neighbouring frames

            nw, nh = max(1, round((x1 - x0) * scale)), max(1, round((y1 - y0) * scale))
            crop = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((FRAME_SIZE, FRAME_SIZE, 4), np.uint8)
            ox = (FRAME_SIZE - nw) // 2
            canvas[FRAME_SIZE - nh:, ox:ox + nw] = crop
            frames.append(canvas)
        out[row] = frames
    return out


def generate_all(sprites_dir: Path):
    frames = slice_frames()

    # Start clean: folders from an older mapping (or the placeholders)
    # would otherwise linger next to the new ones.
    if sprites_dir.exists():
        for old in sprites_dir.iterdir():
            if old.is_dir():
                shutil.rmtree(old)

    saved = {}

    def save(state: str, imgs):
        d = sprites_dir / state
        d.mkdir(parents=True, exist_ok=True)
        for i, im in enumerate(imgs):
            cv2.imwrite(str(d / f"{state}_{i}.png"), im)
        saved[state] = imgs

    for state, (row, indices) in _STATE_SOURCES.items():
        src = frames[row]
        save(state, [src[i] for i in indices if i < len(src)] if indices else src)
    for left, right in _MIRRORED.items():
        save(left, [cv2.flip(f, 1) for f in saved[right]])
    for row in _EXTRA_ROWS:
        save(row.lower(), frames[row])


if __name__ == "__main__":
    generate_all(Path(__file__).resolve().parent / "sprites")
