"""Map every player AnimationClip to the sprites it shows on each renderer path.

usage: python -P -E clip_map.py <out.txt> [<out.json>]
"""
import json
import os
import re
import sys
import zlib
from collections import defaultdict

import UnityPy

sys.path.insert(0, os.path.dirname(__file__))
from game_paths import AA, DUMP, MAIN, ROOT as ROOT_PATH, source_bundle  # noqa: E402
ROOT = ROOT_PATH.as_posix()
CLIPS_MAIN = "team17_auto_base_characters_assets_player.bundle"
PATHS = {zlib.crc32(p.encode()): p or "<root>" for p in (
    "", "Sprite", "Flip/Arm Sprite", "Flip", "AnimRoot", "AnimRoot/AnimRoot_Flip",
    "AnimRoot/AnimRoot_Flip/Aiming", "AnimRoot/AnimRoot_Flip/Aiming/Head", "AnimRoot/AnimRoot_Flip/Aiming/Arms",
    "AnimRoot/AnimRoot_Flip/Aiming/Arms/Arm Rear", "AnimRoot/AnimRoot_Flip/Aiming/Arms/Arm Front",
    "ActiveUsedItemAnimNode/Item", "ActiveUsedItemAnimNode", "WeaponsAnimNode")}


def cab_of(env):
    return [name for name in env.files[list(env.files)[0]].files if not name.endswith((".resS", ".resource"))][0]


def sprite_map():
    """{(cab, path_id): (name, bundle)} for the player bundle and every patch bundle with sprites."""
    out = {}
    fns = [MAIN] + [l.split(" ", 1)[0] for l in open(DUMP / "patch_bundle_sprites.txt", encoding="utf-8")]
    for fn in fns:
        env = UnityPy.load(source_bundle(fn))
        cab = cab_of(env).lower()
        for o in env.objects:
            if o.type.name == "Sprite":
                out[(cab, o.path_id)] = (o.peek_name(), fn)
    return out


def compress(names):
    """['A00','A01','A02','B'] -> 'A00-02, B' keeping first-seen order of groups."""
    groups = {}
    for n in names:
        m = re.match(r"(.*?)(\d+)(_flipped)?$", n)
        key = (m.group(1), m.group(3) or "") if m else (n, "")
        groups.setdefault(key, []).append(int(m.group(2)) if m else None)
    parts = []
    for (base, suf), idx in groups.items():
        nums = sorted(set(i for i in idx if i is not None))
        parts.append(f"{base}{suf}[{nums[0]}-{nums[-1]} n{len(nums)}]" if nums else base + suf)
    return ", ".join(parts)


def main():
    smap = sprite_map()
    print("sprites mapped", len(smap))
    clip_bundles = [CLIPS_MAIN]
    for line in open(DUMP / "scan_clips.txt", encoding="utf-8"):
        fn = line.split(" ", 1)[0]
        if fn.startswith("team17_auto_patch") and "Player_" in line:
            clip_bundles.append(fn)
    rows, data = [], {}
    for fn in clip_bundles:
        env = UnityPy.load(source_bundle(fn))
        for o in env.objects:
            if o.type.name != "AnimationClip":
                continue
            t = o.read_typetree()
            ext = [e.path.split("/")[-1].lower() for e in o.assets_file.externals]
            cab = cab_of(env).lower()
            bc = t["m_ClipBindingConstant"]
            paths = sorted({PATHS.get(b["path"], f"#{b['path']}") for b in bc["genericBindings"] if b["isPPtrCurve"]})
            names = []
            for v in bc["pptrCurveMapping"]:
                key = (cab, v["m_PathID"]) if v["m_FileID"] == 0 else (ext[v["m_FileID"] - 1], v["m_PathID"])
                names.append(smap.get(key, (f"?{key[0][:12]}:{v['m_PathID']}", ""))[0])
            data[t["m_Name"]] = {"paths": paths, "sprites": names,
                                 "length": t["m_MuscleClip"]["m_StopTime"], "bundle": fn}
            rows.append(f"{t['m_Name']}  [{fn[:70]}]  len={t['m_MuscleClip']['m_StopTime']:.2f}\n"
                        f"    paths: {paths}\n    sprites: {compress(names)}\n")
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write("".join(sorted(rows)))
    if len(sys.argv) > 2:
        json.dump(data, open(sys.argv[2], "w"), indent=0)
    print("clips", len(rows))


if __name__ == "__main__":
    main()
