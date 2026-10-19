"""Verify a rebuilt player bundle: every full-rect sprite mesh must cover its texture exactly.

usage: python -P -E verify_frog_bundle.py <bundle> <sheet.png> [sample_count] [original.bundle]
"""
import random
import struct
import sys

import UnityPy
from PIL import Image, ImageDraw


def main():
    env = UnityPy.load(sys.argv[1])
    by_id = {o.path_id: o for o in env.objects}
    originals = ({o.path_id: o for o in UnityPy.load(sys.argv[4]).objects} if len(sys.argv) > 4 else {})
    if originals and set(originals) != set(by_id):
        raise ValueError("The rebuilt bundle has a different object set")
    n_sample = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    bad, quads, tight, total, unchanged_quads = [], 0, 0, 0, 0
    sample = []
    for o in env.objects:
        if o.type.name != "Sprite":
            continue
        total += 1
        t = o.read_typetree()
        rd = t["m_RD"]
        vd = rd["m_VertexData"]
        if vd["m_VertexCount"] != 4:
            tight += 1
            continue
        if originals and o.get_raw_data() == originals[o.path_id].get_raw_data():
            # Original weapon/effect quads can use packed UVs; only redrawn geometry must be full-rect.
            unchanged_quads += 1
            continue
        quads += 1
        data = bytes(vd["m_DataSize"])
        pos = [struct.unpack_from("<3f", data, i * 12)[:2] for i in range(4)]
        ppu = t["m_PixelsToUnits"]
        ut = rd["uvTransform"]
        px = [(x * ut["x"] + ut["y"], y * ut["z"] + ut["w"]) for x, y in pos]
        w, h = t["m_Rect"]["width"], t["m_Rect"]["height"]
        xs, ys = [p[0] for p in px], [p[1] for p in px]
        ok = (abs(min(xs)) < 0.01 and abs(max(xs) - w) < 0.01 and abs(min(ys)) < 0.01 and abs(max(ys) - h) < 0.01
              and abs(ut["x"] - ppu) < 1e-3 and abs(t["m_Pivot"]["x"] * w - ut["y"]) < 0.01
              and abs(t["m_Pivot"]["y"] * h - ut["w"]) < 0.01 and len(bytes(rd["m_IndexBuffer"])) == 12
              and rd["m_SubMeshes"][0]["indexCount"] == 6 and (rd["settingsRaw"] & 64) == 0)
        tex = rd["texture"]
        if not ok:
            bad.append(t["m_Name"])
        sample.append((t["m_Name"], tex, t))
    print(f"sprites={total} full-rect={quads} untouched-tight={tight} unchanged-quads={unchanged_quads} bad={len(bad)} {bad[:10]}")
    random.seed(7)
    picks = random.sample(sample, min(n_sample, len(sample)))
    tiles = []
    for name, tex_ptr, t in picks:
        tex = by_id[tex_ptr["m_PathID"]].read()
        img = tex.image.convert("RGBA")
        if img.size != (int(t["m_Rect"]["width"]), int(t["m_Rect"]["height"])):
            bad.append(name + " (texture size != rect)")
        bg = Image.new("RGBA", img.size, (95, 95, 95, 255))
        bg.alpha_composite(img)
        d = ImageDraw.Draw(bg)
        x, y = t["m_Pivot"]["x"] * img.width, img.height - t["m_Pivot"]["y"] * img.height
        d.ellipse([x - 8, y - 8, x + 8, y + 8], outline=(255, 0, 0, 255), width=3)
        d.text((5, 5), name, fill=(255, 255, 0, 255))
        bg.thumbnail((300, 300))
        tiles.append(bg)
    cols = 10
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGBA", (300 * cols, 300 * rows), (40, 40, 40, 255))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * 300, (i // cols) * 300 + 300 - tile.height))
    sheet.save(sys.argv[2])
    print("sheet", sys.argv[2], sheet.size, "problems:", bad[:10])
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
