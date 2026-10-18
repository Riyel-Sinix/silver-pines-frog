"""Print face-visibility features per frame to classify side / front / back views.

usage: python -P -E view_probe.py <Group:first-last> [...]
"""
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.argv, ARGS = sys.argv[:1] + ["preview", "/dev/null"], sys.argv[1:]
import frogify as F  # noqa: E402
from seq_sheet import load_all  # noqa: E402
import UnityPy  # noqa: E402


def features(rgba):
    rgb = rgba[..., :3].astype(np.float32)
    a = rgba[..., 3]
    sil = F.silhouette(a)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    h = a.shape[0]
    top = h - 1 - sil["y1"]
    H = sil["y1"] - sil["y0"]
    rows = slice(max(0, int(top)), int(top + 0.15 * H))
    op = a[rows] > 200
    hair = op & (lum[rows] < 45)
    skin = op & F.skin_mask(rgb[rows], lum[rows])
    shirt_rows = slice(int(top + 0.15 * H), int(top + 0.32 * H))
    so = a[shirt_rows] > 200
    mx, mn = rgb[shirt_rows].max(axis=2), rgb[shirt_rows].min(axis=2)
    shirt = so & (lum[shirt_rows] > 170) & ((mx - mn) < 30)
    ys, xs = np.nonzero(op)
    hw = (xs.max() - xs.min() + 1) if len(xs) else 1
    hx = np.nonzero(hair)[1].mean() if hair.any() else np.nan
    sx = np.nonzero(skin)[1].mean() if skin.any() else np.nan
    return {"skin_frac": skin.sum() / max(1, skin.sum() + hair.sum()), "off": (sx - hx) / hw,
            "shirt": shirt.sum() / max(1, so.sum()), "lean": sil["lean"]}


def main():
    index = load_all()
    envs = {}
    for spec in ARGS:
        group, rng = spec.split(":")[:2]
        a, b = (int(x) for x in rng.split("-"))
        for i in range(a, b + 1):
            cands = [n for n in index if re.fullmatch(re.escape(group) + r"0*" + str(i), n)]
            if not cands:
                continue
            path, pid = index[cands[0]]
            env = envs.setdefault(path, UnityPy.load(path))
            spr = [o for o in env.objects if o.path_id == pid][0].read()
            f = features(np.asarray(spr.m_RD.texture.read().image.convert("RGBA")))
            print(f"{cands[0]:28s} skin={f['skin_frac']:.2f} off={f['off']:+.2f} shirt={f['shirt']:.3f} lean={f['lean']:+.0f}")


if __name__ == "__main__":
    main()
