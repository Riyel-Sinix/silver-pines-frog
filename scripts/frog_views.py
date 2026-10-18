"""Cut the extra frog views out of the user's reference images (white backgrounds).

  frogmod/source/frog_turnaround.png : side | front | back (the sheet's own labels are shuffled)
  frogmod/source/frog_glance.png     : 3/4 head glancing at the viewer ("惊鸿一瞥")

usage: python -P -E frog_views.py <out_dir> <preview.png>
writes front.png, back.png (whole figures), glance_head.png, views.json
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")  # the repository
SRC = ROOT + "/frogmod/source"
FIGURES = {"front": (80, 18, 164, 184), "back": (164, 18, 258, 184)}  # x0, y0, x1, y1 in the 259x194 sheet
GLANCE_CROP = (40, 18, 226, 178)  # above the caption


def cutout(img, tol=34):
    """Alpha from the white background, flood-filled from the crop border; grey floor shadow suppressed."""
    rgb = np.asarray(img.convert("RGB")).astype(np.int16)
    h, w = rgb.shape[:2]
    whiteish = (rgb.min(axis=2) > 255 - tol).astype(np.uint8)
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    greyish = ((mx - mn) < 22) & (mn > 150)
    bgcand = (whiteish | greyish).astype(np.uint8)
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flood = bgcand.copy()
    for x in range(w):
        for y in (0, h - 1):
            if flood[y, x] == 1:
                cv2.floodFill(flood, mask, (x, y), 2)
    for y in range(h):
        for x in (0, w - 1):
            if flood[y, x] == 1:
                cv2.floodFill(flood, mask, (x, y), 2)
    bg = flood == 2
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # soften: partial alpha for light pixels on the boundary
    edge = cv2.dilate(bg.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    light = (255 - mn).clip(0, 255) / 120.0
    alpha = np.where(edge & ~bg, np.clip(light * 255, 60, 255), alpha).astype(np.uint8)
    out = np.dstack([rgb.astype(np.uint8), alpha])
    n, lab, st, _ = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8))
    if n > 2:
        keep = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        out[..., 3][lab != keep] = 0
    return out


def defringe(src, band=2):
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


def trim(arr):
    ys, xs = np.nonzero(arr[..., 3] > 0)
    return arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


BACK_TORSO = ((40, 9.0), (50, 16.0), (90, 16.0), (103, 18.5))  # (y, x of the torso's left edge), arms outside
PARTS = ROOT + "/frogmod/parts"
SIDE_EYE, GLANCE_EYE = (37.0, 13.0), (75.0, 57.0)    # near-eye centres: side cut-out / glance crop
SIDE_MOUTH_Y, GLANCE_TOP_Y, GLANCE_MOUTH_Y = 22.0, 12.0, 105.0


def split_legs(fig, min_gap=1):
    """Body rows above the crotch, legs below split at the gap between them (left / right on screen)."""
    a = fig[..., 3]
    h, w = a.shape
    lo, hi = int(0.2 * w), int(0.8 * w)
    hip = None
    for y in range(int(0.55 * h), h):
        cols = np.nonzero(a[y, lo:hi] > 40)[0]
        if len(cols) > 1 and np.diff(cols).max() > min_gap:
            hip = y
            break
    split = np.full(h, w / 2.0)
    for y in range(hip, h):
        cols = np.nonzero(a[y, lo:hi] > 40)[0] + lo
        if len(cols) > 1 and np.diff(cols).max() > min_gap:
            g = np.argmax(np.diff(cols))
            split[y] = (cols[g] + cols[g + 1]) / 2.0
        else:
            split[y] = split[y - 1]
    yy, xx = np.mgrid[0:h, 0:w]
    legs = yy >= hip  # the hanging hands end above the crotch
    left = legs & (xx < split[:, None])
    right = legs & ~left
    body_alpha = np.clip((hip + 4 - yy) / 5.0, 0, 1)
    body_alpha = np.where(legs, body_alpha, 1.0)
    return hip, body_alpha, left, right


def layer(fig, mask):
    out = fig.copy()
    out[..., 3] = (out[..., 3] * mask).astype(np.uint8)
    return out


def view_parts(fig, name, meta):
    hip, body_alpha, left, right = split_legs(fig)
    h, w = fig.shape[:2]
    layers = {f"{name}_body": layer(fig, body_alpha), f"{name}_leg_l": layer(fig, left.astype(np.float32)),
              f"{name}_leg_r": layer(fig, right.astype(np.float32))}
    m = {"size": [w, h], "hip_y": hip, "hip_x": w / 2.0}
    if name == "back":
        ys, xl = zip(*BACK_TORSO)
        yy, xx = np.mgrid[0:h, 0:w]
        edge = np.interp(yy, ys, xl)
        rows = (yy >= ys[0]) & (yy <= ys[-1])
        arms = rows & ((xx < edge) | (xx > (w - 1) - edge))
        noarms = layer(fig, body_alpha * ~arms)
        layers["back_body_noarms"] = noarms
        m["shoulders"] = [[edge[50, 0] + 1.0, 49.0], [w - 2.0 - edge[50, 0], 49.0]]
    for k, v in layers.items():
        Image.fromarray(v, "RGBA").save(f"{PARTS}/{k}.png")
    meta[name] = m
    return list(layers.values())


GLANCE_SNOUT_X, GLANCE_RIGHT_X = 10.0, 186.0   # glance crop: snout tip, right border (the head continues)
GLANCE_EYES, GLANCE_EYE_R = ((75.0, 57.0), (14.0, 56.0)), 24.0  # near / far eye centres, iris radius (crop px)
SIDE_SNOUT_X, SIDE_BACK_X = 22.0, 75.0         # side cut-out head: snout tip, back of the head at eye level


GLANCE_BULGE = ((1.4, 12.5), (1.6, 8.0))  # near / far eye: magnification, radius (cut-out px) — reads at game size


def bulge(arr, centre, radius, k):
    """Magnify by k around centre, easing back to no change at radius (a goggle eye; the outline bulges too)."""
    a = arr.astype(np.float32).copy()
    holes = (a[..., 3] < 1).astype(np.uint8)
    a[..., :3] = cv2.inpaint(np.clip(a[..., :3], 0, 255).astype(np.uint8), holes, 3, cv2.INPAINT_TELEA)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - centre[0], yy - centre[1]
    t = np.clip(np.sqrt(dx * dx + dy * dy) / radius, 0.0, 1.0)
    f = 1.0 / k + (1.0 - 1.0 / k) * t * t * (3.0 - 2.0 * t)
    out = cv2.remap(a, centre[0] + dx * f, centre[1] + dy * f, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    out[..., 3] = np.where(t >= 1.0, arr[..., 3], out[..., 3])
    return np.clip(out, 0, 255)


def glance_body():
    """The side body (hands on the belly) with its head turned to the viewer ("惊鸿一瞥"): the glance crop spans
    the side head from snout to back of head, is colour-matched to the side frog, and feathers into the neck."""
    side = np.asarray(Image.open(PARTS + "/body_arms.png").convert("RGBA")).astype(np.float32)
    head = Image.open(PARTS + "/glance_head.png").convert("RGBA")
    s = (SIDE_BACK_X - SIDE_SNOUT_X) / (GLANCE_RIGHT_X - GLANCE_SNOUT_X)
    small = np.asarray(head.resize((max(1, int(round(head.width * s))), max(1, int(round(head.height * s)))),
                                   Image.LANCZOS)).astype(np.float32)
    ox, oy = int(round(SIDE_SNOUT_X - GLANCE_SNOUT_X * s)), int(round(-GLANCE_TOP_Y * s))
    sh, sw = small.shape[:2]
    solid = cv2.erode((small[..., 3] > 250).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0

    def skin(img, box):
        x0, y0, x1, y1 = box
        p = img[y0:y1, x0:x1].reshape(-1, 4)
        return p[(p[:, 3] > 200) & (p[:, 0] > 150) & (p[:, 0] > p[:, 1]) & (p[:, 1] > p[:, 2])][:, :3]
    g, sd = skin(small, (0, 0, sw, sh)), skin(side, (20, 0, 80, 40))
    rgb = cv2.medianBlur(small[..., :3].astype(np.uint8), 3).astype(np.float32) - g.mean(0) + sd.mean(0)
    lum_max = np.percentile(sd @ np.array([0.299, 0.587, 0.114]), 97)
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    rgb *= np.minimum(1.0, lum_max / np.maximum(lum, 1.0))[..., None]  # tame the rim light
    yy1, xx1 = np.mgrid[0:sh, 0:sw]
    near_eyes = np.zeros((sh, sw), bool)
    for ex, ey in GLANCE_EYES:
        near_eyes |= (xx1 - ex * s) ** 2 + (yy1 - ey * s) ** 2 < (GLANCE_EYE_R * s) ** 2
    eye = solid & near_eyes & ((small[..., 1] > small[..., 0] + 10) | (small[..., :3].max(axis=2) < 70))
    small[..., :3] = np.where(eye[..., None], small[..., :3], np.clip(rgb, 0, 255))
    edge = (small[..., 3] > 0) & ~solid
    small[..., :3] = np.where(edge[..., None], np.clip(rgb, 0, 255), small[..., :3])  # no stray eye colours
    yy, xx = np.mgrid[0:sh, 0:sw]
    feather = np.clip((0.78 * sh - yy) / (0.22 * sh), 0, 1) * np.clip((sw - xx) / (0.16 * sw), 0, 1)
    out = side.copy()
    ty0, tx0 = max(0, oy), max(0, ox)
    ty1, tx1 = min(out.shape[0], oy + sh), min(out.shape[1], ox + sw)
    reg = out[ty0:ty1, tx0:tx1]
    sm = small[ty0 - oy:ty1 - oy, tx0 - ox:tx1 - ox]
    fe = feather[ty0 - oy:ty1 - oy, tx0 - ox:tx1 - ox]
    a = sm[..., 3:4] / 255.0 * fe[..., None]
    reg[..., :3] = reg[..., :3] * (1 - a) + sm[..., :3] * a
    reg[..., 3] = np.maximum(reg[..., 3], sm[..., 3] * (fe > 0.5))
    out[ty0:ty1, tx0:tx1] = reg
    # off-palette pixels (JPEG noise turned blue / magenta / cyan) take the median of their good neighbours
    r, gg, b = out[..., 0], out[..., 1], out[..., 2]
    yy2, xx2 = np.mgrid[0:out.shape[0], 0:out.shape[1]]
    in_eyes = np.zeros(out.shape[:2], bool)
    for ex, ey in GLANCE_EYES:  # near and far eye centres in the glance crop
        in_eyes |= (xx2 - (ox + ex * s)) ** 2 + (yy2 - (oy + ey * s)) ** 2 < (GLANCE_EYE_R * s) ** 2
    iris = in_eyes & (gg > r + 10) & (gg > b + 10)
    bad = (out[..., 3] > 0) & ~iris & (out[..., :3].max(axis=2) > 70) & ((b > gg - 4) | (r < gg - 6))
    bad[oy + sh:] = False
    good = (out[..., 3] > 200) & ~bad
    k = np.ones((7, 7), np.float32)
    num = cv2.filter2D(out[..., :3] * good[..., None], -1, k, borderType=cv2.BORDER_CONSTANT)
    den = cv2.filter2D(good.astype(np.float32), -1, k, borderType=cv2.BORDER_CONSTANT)
    fixable = bad & (den > 0.5)
    out[..., :3][fixable] = num[fixable] / den[fixable][:, None]
    for (ex, ey), (k, radius) in zip(GLANCE_EYES, GLANCE_BULGE):  # centred on the iris that is actually visible
        cx, cy = ox + ex * s, oy + ey * s
        disc = iris & ((xx2 - cx) ** 2 + (yy2 - cy) ** 2 < (GLANCE_EYE_R * s) ** 2)
        if disc.sum() >= 3:
            cx, cy = float(xx2[disc].mean()), float(yy2[disc].mean())
        out = bulge(out, (cx, cy), radius, k)
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(PARTS + "/body_glance.png")
    return out.astype(np.uint8)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    sheet = Image.open(SRC + "/frog_turnaround.png").convert("RGB")
    meta = {}
    tiles = []
    for name, box in FIGURES.items():
        fig = trim(defringe(cutout(sheet.crop(box))))
        Image.fromarray(fig, "RGBA").save(f"{out}/{name}.png")
        tiles += view_parts(fig, name, meta)
    glance = Image.open(SRC + "/frog_glance.png").convert("RGB").crop(GLANCE_CROP)
    head = defringe(cutout(glance))
    Image.fromarray(head, "RGBA").save(f"{PARTS}/glance_head.png")
    tiles.append(glance_body())
    json.dump(meta, open(f"{PARTS}/views.json", "w"), indent=1)
    S = 4
    W = sum(t.shape[1] * S + 12 for t in tiles)
    H = max(t.shape[0] * S for t in tiles)
    prev = Image.new("RGBA", (W, H), (70, 70, 70, 255))
    x = 0
    for t in tiles:
        im = Image.fromarray(t, "RGBA")
        prev.alpha_composite(im.resize((im.width * S, im.height * S), Image.NEAREST), (x, 0))
        x += im.width * S + 12
    prev.save(sys.argv[2])
    print(meta)


if __name__ == "__main__":
    main()
