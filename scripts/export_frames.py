"""Export selected sprite textures from a bundle to a labelled contact sheet (pivot marked in red).

usage: python -P -E export_frames.py <bundle> <out.png> <name> [<name> ...]
"""
import sys

import UnityPy
from PIL import Image, ImageDraw


def main():
    env = UnityPy.load(sys.argv[1])
    want = sys.argv[3:]
    found = {}
    for o in env.objects:
        if o.type.name == "Sprite":
            s = o.read()
            if s.m_Name in want:
                found[s.m_Name] = s
    tiles = []
    for name in want:
        s = found.get(name)
        if s is None:
            print("missing", name)
            continue
        tex = s.m_RD.texture.read()
        img = tex.image.convert("RGBA")
        bg = Image.new("RGBA", img.size, (90, 90, 90, 255))
        bg.alpha_composite(img)
        d = ImageDraw.Draw(bg)
        px = s.m_Pivot.x * img.width
        py = img.height - s.m_Pivot.y * img.height  # Unity origin is bottom-left
        d.ellipse([px - 8, py - 8, px + 8, py + 8], outline=(255, 0, 0, 255), width=3)
        d.text((6, 6), f"{name} {img.width}x{img.height}", fill=(255, 255, 0, 255))
        tiles.append(bg)
    h = max(t.height for t in tiles)
    sheet = Image.new("RGBA", (sum(t.width for t in tiles) + 10 * len(tiles), h), (40, 40, 40, 255))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 10
    sheet.thumbnail((2400, 1000))
    sheet.save(sys.argv[2])
    print("saved", sys.argv[2], sheet.size)


if __name__ == "__main__":
    main()
