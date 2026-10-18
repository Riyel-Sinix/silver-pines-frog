"""Print the silhouette measurements that decide hang / swim arm modes for the given groups.

usage: python -P -E hang_probe.py Group [Group ...]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.argv, ARGS = sys.argv[:1] + ["preview", "/dev/null"], sys.argv[1:]
import frogify as F  # noqa: E402
from seq_sheet import load_all  # noqa: E402
import UnityPy  # noqa: E402


def main():
    index = load_all()
    envs = {}
    for name in sorted(index):
        group = F.group_of(name)
        if group not in ARGS:
            continue
        path, pid = index[name]
        env = envs.setdefault(path, UnityPy.load(path))
        spr = [o for o in env.objects if o.path_id == pid][0].read()
        rgba = np.asarray(spr.m_RD.texture.read().image.convert("RGBA"))
        ppu = spr.m_PixelsToUnits
        sil = F.silhouette(rgba[..., 3])
        if sil is None:
            print(name, "empty")
            continue
        hs = (sil["y1"] - sil["y0"]) / ppu
        hh = rgba.shape[0]
        top = hh - sil["y1"]
        rows = rgba[top:top + max(2, int(0.05 * ppu)), :, 3] > F.ALPHA_CUT
        xs = np.nonzero(rows.any(axis=0))[0]
        width = (xs.max() - xs.min() + 1) / ppu if len(xs) else -1
        hang = F.hang_target(rgba[..., 3], sil, ppu)
        print(f"{name:34s} h={hs:4.2f} lean={sil['lean']:6.1f} elong={sil['elong']:4.2f} "
              f"upright={F.upright(sil)!s:5s} topw={width:4.2f} hang={'-' if hang is None else 'yes'} "
              f"n6={'yes' if F.weapon_node(name) else '-'}")


if __name__ == "__main__":
    main()
