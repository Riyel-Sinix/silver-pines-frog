"""Split the frog cut-out into layers: body (with / without arms), front leg, back leg.

usage: python -P -E frog_parts.py <frog_cutout.png> <out_dir> <preview.png>
The cut-out faces left. Coordinates below are in cut-out pixels (101x200, top-left origin).
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

HIP_Y = 142            # first row where the two legs are separate
BODY_OVERLAP = 5       # body layer reaches this many rows below the hip
HAND_BOX = (0, 76, 40, 110)          # both hands sit in front of the belly
FOREARM_BOX = (14, 70, 64, 104)      # forearm crossing the belly
BELLY_EDGE_X = 7                     # the far hand sticks out past the belly outline here
BELLY_CURVE = (66, 104, 16, 7)       # rows y0..y1: belly outline x goes from x_top to x_belly (convex)
CREASE_BOX = (44, 44, 82, 104)       # upper-arm crease and elbow shadow


def defringe(src, band=2):
    """Recolour the outer edge ring from the solid interior next to it: the cut-out from a white background
    leaves light, partly or fully opaque edge pixels that read as a white halo in game."""
    a = src[..., 3]
    opaque = a > 0
    inner = (cv2.erode(opaque.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=band) > 0) & (a > 230)
    rgb = src[..., :3].astype(np.float32)
    k = np.ones((7, 7), np.float32)
    num = cv2.filter2D(rgb * inner[..., None], -1, k, borderType=cv2.BORDER_CONSTANT)
    den = cv2.filter2D(inner.astype(np.float32), -1, k, borderType=cv2.BORDER_CONSTANT)
    avg = num / np.maximum(den, 1e-6)[..., None]
    w = np.array([0.299, 0.587, 0.114], np.float32)
    fix = opaque & ~inner & (den > 0.5) & ((a <= 230) | (rgb @ w > avg @ w + 10))
    rgb[fix] = avg[fix]
    src[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return src


def main():
    src = defringe(np.asarray(Image.open(sys.argv[1]).convert("RGBA")).copy())
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    h, w = src.shape[:2]
    rgb = src[..., :3].astype(np.float32)
    alpha = src[..., 3]
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1)
    yy, xx = np.mgrid[0:h, 0:w]

    def box(b):
        x0, y0, x1, y1 = b
        return (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)

    opaque = alpha > 20
    hands = box(HAND_BOX) & opaque & (lum < 120)
    forearm = box(FOREARM_BOX) & opaque & (sat > 0.55) & (lum > 120)  # yellow arm over the cream belly
    arm = hands | forearm
    arm = cv2.dilate(arm.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1).astype(bool) & opaque

    # arm-less body: cut the part of the far hand outside the belly, inpaint the rest from the belly / body
    noarms = src.copy()
    outside = arm & (xx < BELLY_EDGE_X)
    noarms[outside, 3] = 0
    fill = (arm & ~outside).astype(np.uint8) * 255
    bgr = cv2.cvtColor(noarms[..., :3], cv2.COLOR_RGB2BGR)
    painted = cv2.inpaint(bgr, fill, 4, cv2.INPAINT_TELEA)
    noarms[..., :3] = cv2.cvtColor(painted, cv2.COLOR_BGR2RGB)

    # the far forearm still sticks out of the belly outline above the hands: cut along a smooth belly curve
    y0, y1, x_top, x_belly = BELLY_CURVE
    curve = x_belly + (x_top - x_belly) * np.clip((y1 - yy) / float(y1 - y0), 0, 1) ** 2
    noarms[(yy >= y0) & (yy <= y1) & (xx < curve - 0.5), 3] = 0

    # smooth the upper-arm crease and the elbow shadow so no arm stump remains
    lum2 = (0.299 * noarms[..., 0] + 0.587 * noarms[..., 1] + 0.114 * noarms[..., 2]).astype(np.float32)
    ref = cv2.GaussianBlur(lum2, (0, 0), 7)
    crease = box(CREASE_BOX) & (noarms[..., 3] > 200) & (lum2 < ref - 8)
    crease = cv2.dilate(crease.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & (noarms[..., 3] > 200)
    bgr = cv2.cvtColor(noarms[..., :3], cv2.COLOR_RGB2BGR)
    painted = cv2.inpaint(bgr, crease.astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
    noarms[..., :3] = cv2.cvtColor(painted, cv2.COLOR_BGR2RGB)

    # legs: below HIP_Y, split per row at the gap between the two legs (front leg = left, facing left)
    split = np.full(h, 51, dtype=int)
    for y in range(HIP_Y, h):
        cols = np.nonzero(alpha[y] > 20)[0]
        if len(cols) < 2:
            continue
        gaps = np.nonzero(np.diff(cols) > 1)[0]
        if len(gaps) and y < 172:
            g = gaps[np.argmax(np.diff(cols)[gaps])]
            split[y] = (cols[g] + cols[g + 1]) // 2
        else:
            split[y] = split[y - 1] if y > HIP_Y else 51
    legs = yy >= HIP_Y
    front = legs & (xx < split[:, None])
    back = legs & ~front

    def layer(img, mask):
        lay = img.copy()
        lay[..., 3] = (lay[..., 3] * mask).astype(np.uint8)
        return Image.fromarray(lay, "RGBA")

    # the body overlaps the leg tops and fades out over the overlap, so no seam shows at the hip line
    body_mask = np.clip((HIP_Y + BODY_OVERLAP - yy) / float(BODY_OVERLAP + 1), 0, 1)
    layers = {
        "body_arms": layer(src, body_mask),
        "body_noarms": layer(noarms, body_mask),
        "leg_front": layer(src, front.astype(np.float32)),
        "leg_back": layer(src, back.astype(np.float32)),
    }
    for k, im in layers.items():
        im.save(os.path.join(out, f"{k}.png"))

    def foot(mask, y_from):
        ys, xs = np.nonzero(mask & (yy >= y_from) & opaque)
        return float(xs.mean()), float(ys.max() + 1)

    hip_x = float(np.nonzero(opaque[HIP_Y - 2])[0].mean())
    ff_x, ff_bottom = foot(front, 172)
    bf_x, bf_bottom = foot(back, 176)
    meta = {"size": [w, h], "hip_y": HIP_Y, "hip_x": hip_x, "front_foot_x": ff_x, "back_foot_x": bf_x,
            "front_foot_bottom": ff_bottom, "back_foot_bottom": bf_bottom}
    json.dump(meta, open(os.path.join(out, "parts.json"), "w"), indent=1)
    print(meta)

    S = 4
    tiles = [Image.fromarray(src, "RGBA")] + list(layers.values())
    prev = Image.new("RGBA", ((w + 6) * len(tiles) * S, h * S), (70, 70, 70, 255))
    for i, im in enumerate(tiles):
        prev.alpha_composite(im.resize((w * S, h * S), Image.NEAREST), (i * (w + 6) * S, 0))
    prev.save(sys.argv[3])


if __name__ == "__main__":
    main()
