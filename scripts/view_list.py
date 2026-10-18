"""Print the view (side / front / back / glance) chosen for every frame of the given groups.

usage: python -P -E view_list.py Group [Group ...]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.argv, ARGS = sys.argv[:1] + ["preview", "/dev/null"], sys.argv[1:]
import frogify as F  # noqa: E402
import UnityPy  # noqa: E402


def main():
    env = UnityPy.load(F.ORIG_MAIN)
    by_id = {o.path_id: o for o in env.objects}
    rows = []
    for o in env.objects:
        if o.type.name != "Sprite":
            continue
        t = o.read_typetree()
        name, group = t["m_Name"], F.group_of(t["m_Name"])
        if group not in ARGS:
            continue
        rgba = np.asarray(by_id[t["m_RD"]["texture"]["m_PathID"]].read().image.convert("RGBA"))
        sil = F.silhouette(rgba[..., 3])
        if sil is None:
            continue
        rows.append((name, F.view_of(group, name, rgba, sil), F.face_fraction(rgba, sil)))
    for name, view, f in sorted(rows):
        print(f"{name:28s} {view:7s} face={f:.2f}")


if __name__ == "__main__":
    main()
