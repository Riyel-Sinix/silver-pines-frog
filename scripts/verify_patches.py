"""Verify rebuilt patch bundles: they load, redrawn sprites are exact full-rect quads over same-size textures,
recoloured overlays keep their original mesh and texture size, and the asset list is unchanged.

usage: python -P -E verify_patches.py <built_dir> <original_dir>
"""
import os
import struct
import sys

import UnityPy


def quad_ok(t):
    rd = t["m_RD"]
    vd = rd["m_VertexData"]
    data = bytes(vd["m_DataSize"])
    pos = [struct.unpack_from("<3f", data, i * 12)[:2] for i in range(4)]
    ut = rd["uvTransform"]
    px = [(x * ut["x"] + ut["y"], y * ut["z"] + ut["w"]) for x, y in pos]
    w, h = t["m_Rect"]["width"], t["m_Rect"]["height"]
    xs, ys = [p[0] for p in px], [p[1] for p in px]
    return (abs(min(xs)) < 0.01 and abs(max(xs) - w) < 0.01 and abs(min(ys)) < 0.01 and abs(max(ys) - h) < 0.01
            and abs(ut["x"] - t["m_PixelsToUnits"]) < 1e-3 and abs(t["m_Pivot"]["x"] * w - ut["y"]) < 0.01
            and abs(t["m_Pivot"]["y"] * h - ut["w"]) < 0.01 and len(bytes(rd["m_IndexBuffer"])) == 12
            and rd["m_SubMeshes"][0]["indexCount"] == 6 and (rd["settingsRaw"] & 64) == 0)


def sprites(env):
    by_id = {o.path_id: o for o in env.objects}
    out = {}
    for o in env.objects:
        if o.type.name == "Sprite":
            t = o.read_typetree()
            tex = by_id[t["m_RD"]["texture"]["m_PathID"]].read()
            out[t["m_Name"]] = (t, tex.m_Width, tex.m_Height, tex.m_TextureFormat)
    return out


def main():
    built, orig = sys.argv[1], sys.argv[2]
    fns = [l.strip() for l in open(os.path.join(built, "bundles.txt"), encoding="utf-8") if l.strip()]
    problems, quads, kept_mesh = [], 0, 0
    for fn in fns:
        try:
            nb, ob = UnityPy.load(os.path.join(built, fn)), UnityPy.load(os.path.join(orig, fn))
        except Exception as e:  # noqa: BLE001
            problems.append(f"{fn}: load {e}")
            continue
        if sorted((o.type.name, o.path_id) for o in nb.objects) != sorted((o.type.name, o.path_id) for o in ob.objects):
            problems.append(f"{fn}: object list changed")
        ns, os_ = sprites(nb), sprites(ob)
        for name, (t, w, h, fmt) in ns.items():
            ot = os_[name][0]
            if t["m_RD"]["m_VertexData"]["m_VertexCount"] == 4 and ot["m_RD"]["m_VertexData"]["m_VertexCount"] != 4:
                quads += 1
                if not quad_ok(t) or (w, h) != (int(t["m_Rect"]["width"]), int(t["m_Rect"]["height"])):
                    problems.append(f"{fn}: {name} bad quad/size")
            else:
                kept_mesh += 1
                if (w, h) != (os_[name][1], os_[name][2]) or t["m_Rect"] != ot["m_Rect"]:
                    problems.append(f"{fn}: {name} overlay size/rect changed")
    print(f"bundles={len(fns)} redrawn quads={quads} kept meshes={kept_mesh} problems={len(problems)}")
    for p in problems[:30]:
        print("  ", p)


if __name__ == "__main__":
    main()
