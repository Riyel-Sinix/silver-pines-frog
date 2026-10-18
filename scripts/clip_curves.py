"""Decode the player's compiled AnimationClips: for every body sprite, the SpriteAnimNodes values (m_node0..9,
m_ang0..9 on the "Sprite" object) at the times that sprite is shown.

Compiled clips keep their curves in m_MuscleClip (streamed cubic keys, dense samples, constants) addressed by
m_ClipBindingConstant.genericBindings; attributes are CRC32 hashes of the property path ("m_node6.x").

usage: python -P -E clip_curves.py <out.json>
"""
import json
import os
import struct
import sys
import zlib
from collections import defaultdict

import numpy as np
import UnityPy

sys.path.insert(0, os.path.dirname(__file__))
from clip_map import AA, CLIPS_MAIN, ROOT, cab_of, sprite_map  # noqa: E402

SPRITE_PATH = zlib.crc32(b"Sprite")
NODE_ATTRS = {zlib.crc32(f"m_node{i}.{c}".encode()): (f"n{i}", c) for i in range(10) for c in "xy"}
NODE_ATTRS.update({zlib.crc32(f"m_ang{i}".encode()): (f"n{i}", "a") for i in range(10)})


def curve_owners(bindings):
    """Global curve index -> (binding index, component)."""
    owners = []
    for bi, b in enumerate(bindings):
        n = 1
        if b["typeID"] == 4:
            n = {1: 3, 2: 4, 3: 3, 4: 3}.get(b["attribute"], 1)
        owners += [(bi, k) for k in range(n)]
    return owners


def streamed_keys(clip):
    """[(time, curve, coeff[4])] from the streamed clip (first/last frames are +-inf sentinels)."""
    data = struct.pack(f"<{len(clip['data'])}I", *clip["data"])
    out, pos = [], 0
    while pos + 8 <= len(data):
        t, n = struct.unpack_from("<fi", data, pos)
        pos += 8
        for _ in range(n):
            idx, c0, c1, c2, c3 = struct.unpack_from("<i4f", data, pos)
            pos += 20
            if abs(t) < 1e30:
                out.append((t, idx, (c0, c1, c2, c3)))
    return out


def decode(tree):
    """{curve index: sorted [(t, coeff)]} for streamed, {curve: [(t, value)]} for dense/constant."""
    mc = tree["m_MuscleClip"]
    clip = mc["m_Clip"]["data"]
    st, de, co = clip["m_StreamedClip"], clip["m_DenseClip"], clip["m_ConstantClip"]
    curves = defaultdict(list)
    for t, idx, coeff in streamed_keys(st):
        curves[idx].append((t, coeff))
    base = st["curveCount"]
    nd = de["m_CurveCount"]
    arr = de["m_SampleArray"]
    for f in range(de["m_FrameCount"]):
        t = de["m_BeginTime"] + f / de["m_SampleRate"]
        for c in range(nd):
            curves[base + c].append((t, (0.0, 0.0, 0.0, arr[f * nd + c])))
    for c, v in enumerate(co["data"]):
        curves[base + nd + c].append((-1e9, (0.0, 0.0, 0.0, v)))
    for k in curves:
        curves[k].sort(key=lambda x: x[0])
    return curves, mc["m_StopTime"]


def evaluate(keys, t):
    times = [k[0] for k in keys]
    i = max(0, int(np.searchsorted(times, t, side="right")) - 1)
    t0, (c0, c1, c2, c3) = keys[i]
    dt = t - t0 if t0 > -1e8 else 0.0
    return ((c0 * dt + c1) * dt + c2) * dt + c3


def main():
    smap = sprite_map()
    bundles = [CLIPS_MAIN]
    for line in open(ROOT + "/_dump/scan_clips.txt", encoding="utf-8"):
        fn = line.split(" ", 1)[0]
        if fn.startswith("team17_auto_patch") and "Player_" in line:
            bundles.append(fn)
    # clips found by scan_sprite_clips.py in any bundle (the debug-named bundles are loaded by the game too)
    import re as _re
    for fn in _re.findall(r"\[([^\]]+)\]", open(ROOT + "/_dump/all_player_clips.txt", encoding="utf-8").read()):
        full = [f for f in os.listdir(AA) if f.startswith(fn)]
        if len(full) == 1 and full[0] not in bundles:
            bundles.append(full[0])
    samples = defaultdict(lambda: defaultdict(list))  # sprite -> node -> [(x, y, a)]
    clips_used = 0
    for fn in bundles:
        env = UnityPy.load(os.path.join(AA, fn))
        cab = cab_of(env).lower()
        for o in env.objects:
            if o.type.name != "AnimationClip":
                continue
            t = o.read_typetree()
            bc = t["m_ClipBindingConstant"]
            bindings = bc["genericBindings"]
            owners = curve_owners(bindings)
            curves, stop = decode(t)
            ext = [e.path.split("/")[-1].lower() for e in o.assets_file.externals]
            sprite_curve, node_curves = None, defaultdict(dict)
            for ci in curves:
                if ci >= len(owners):
                    continue
                b = bindings[owners[ci][0]]
                if b["path"] != SPRITE_PATH:
                    continue
                if b["isPPtrCurve"]:
                    sprite_curve = ci
                elif b["attribute"] in NODE_ATTRS:
                    node, comp = NODE_ATTRS[b["attribute"]]
                    node_curves[node][comp] = ci
            if sprite_curve is None or not node_curves:
                continue
            clips_used += 1
            mapping = bc["pptrCurveMapping"]
            for kt, coeff in curves[sprite_curve]:
                v = mapping[int(round(coeff[3]))]
                key = (cab, v["m_PathID"]) if v["m_FileID"] == 0 else (ext[v["m_FileID"] - 1], v["m_PathID"])
                name = smap.get(key, (None,))[0]
                if name is None:
                    continue
                tt = max(kt, 0.0) + 1e-4
                for node, comps in node_curves.items():
                    vals = [evaluate(curves[comps[c]], tt) if c in comps else None for c in "xya"]
                    samples[name][node].append(vals)
    out = {}
    for name, nodes in samples.items():
        out[name] = {}
        for node, vals in nodes.items():
            arr = np.array([[np.nan if x is None else x for x in v] for v in vals], dtype=float)
            out[name][node] = {"x": float(np.nanmedian(arr[:, 0])), "y": float(np.nanmedian(arr[:, 1])),
                               "a": float(np.nanmedian(arr[:, 2])) if not np.all(np.isnan(arr[:, 2])) else None,
                               "n": len(vals), "spread": float(np.nanmax(np.nanstd(arr[:, :2], axis=0)))}
    json.dump(out, open(sys.argv[1], "w"), indent=0)
    print(f"clips with nodes: {clips_used}, sprites with node data: {len(out)}")


if __name__ == "__main__":
    main()
