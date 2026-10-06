"""Closed-eye variant of the Meshy texture (the model has no eyelids): the
yellow irises, plus the black pupils and white highlights next to them,
are painted over with the surrounding fur colour."""
import sys

import cv2
import numpy as np

src, dst = sys.argv[1], sys.argv[2]
tex = cv2.imread(src)
b, g, r = [tex[..., i].astype(int) for i in range(3)]
yellow = ((r > 130) & (g > 90) & (b < 120) & (r - b > 60)).astype(np.uint8)
n, lab, st, _ = cv2.connectedComponentsWithStats(yellow)
iris = np.isin(lab, [i for i in range(1, n) if st[i][4] > 150]).astype(np.uint8)
near_eye = cv2.dilate(iris, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (161, 161)))
mx, mn = tex.max(axis=2).astype(int), tex.min(axis=2).astype(int)
pupil = ((mx < 14) | (mn > 170)) & (near_eye > 0)
mask = (iris > 0) | pupil
mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
ring = cv2.dilate(mask, np.ones((15, 15), np.uint8)) - mask
fur = np.median(tex[ring > 0], axis=0).astype(np.uint8)
out = tex.copy()
out[mask > 0] = fur
out = np.where(mask[..., None] > 0, cv2.GaussianBlur(out, (0, 0), 3), out)
cv2.imwrite(dst, out)
print("closed eyes:", int(mask.sum()), "px painted with", fur)
