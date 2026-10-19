"""Find every AnimationClip in every bundle whose sprite curves reference player sprites, whatever its name.

usage: python -P -E scan_sprite_clips.py <out.txt>
"""
import os
import sys

import UnityPy

sys.path.insert(0, os.path.dirname(__file__))
from clip_map import AA, cab_of, compress, source_bundle, sprite_map  # noqa: E402


def main():
    smap = sprite_map()
    player_cabs = {k[0] for k in smap}
    rows = []
    for fn in sorted(os.listdir(AA)):
        if not fn.endswith(".bundle"):
            continue
        try:
            env = UnityPy.load(source_bundle(fn))
        except Exception:  # noqa: BLE001
            continue
        clips = [o for o in env.objects if o.type.name == "AnimationClip"]
        if not clips:
            continue
        try:
            cab = cab_of(env).lower()
        except Exception:  # noqa: BLE001
            continue
        for o in clips:
            ext = [e.path.split("/")[-1].lower() for e in o.assets_file.externals]
            if cab not in player_cabs and not player_cabs & set(ext):
                continue
            try:
                t = o.read_typetree()
            except Exception:  # noqa: BLE001
                continue
            names = []
            for v in t["m_ClipBindingConstant"]["pptrCurveMapping"]:
                key = (cab, v["m_PathID"]) if v["m_FileID"] == 0 else (ext[v["m_FileID"] - 1], v["m_PathID"])
                if key in smap:
                    names.append(smap[key][0])
            if names:
                rows.append(f"{t['m_Name']}  [{fn[:80]}]  len={t['m_MuscleClip']['m_StopTime']:.2f}\n"
                            f"    sprites: {compress(names)}\n")
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write("".join(sorted(rows)))
    print("clips referencing player sprites:", len(rows))


if __name__ == "__main__":
    main()
