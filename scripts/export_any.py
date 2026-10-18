"""Export sprites by name from any bundle in the game's Addressables folder (labelled sheet, pivot in red).

usage: python -P -E export_any.py <out.png> <name> [<name> ...]
Looks names up in _dump/patch_bundle_sprites.txt first, then in the main player bundle.
"""
import os
import re
import sys

import UnityPy
from PIL import Image, ImageDraw

GAME = os.environ.get("SILVER_PINES", r"D:/Games/Silver Pines")  # the game folder; set SILVER_PINES if elsewhere
AA = GAME + "/Carpenter_Data/StreamingAssets/aa/StandaloneWindows64"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")  # the repository
MAIN = "team17_auto_base_characters_compressed_assets_player.bundle"
MAIN_DIR = ROOT + "/frogmod/backup" if os.path.exists(ROOT + "/frogmod/backup/" + MAIN) else AA
INDEX = ROOT + "/_dump/patch_bundle_sprites.txt"


def locate(names):
    where = {}
    for line in open(INDEX, encoding="utf-8"):
        fn = line.split(" ", 1)[0]
        for n in re.findall(r"'([^'(]+)\(", line):
            if n in names:
                where.setdefault(n, fn)
    for n in names:
        where.setdefault(n, MAIN)
    return where


def main():
    names = sys.argv[2:]
    where = locate(set(names))
    by_bundle = {}
    for n in names:
        by_bundle.setdefault(where[n], []).append(n)
    found = {}
    for fn, ns in by_bundle.items():
        env = UnityPy.load(os.path.join(MAIN_DIR if fn == MAIN else AA, fn))
        for o in env.objects:
            if o.type.name == "Sprite":
                s = o.read()
                if s.m_Name in ns:
                    img = s.m_RD.texture.read().image.convert("RGBA")
                    found[s.m_Name] = (s, img)
    tiles = []
    for n in names:
        if n not in found:
            print("missing", n)
            continue
        s, img = found[n]
        bg = Image.new("RGBA", img.size, (90, 90, 90, 255))
        bg.alpha_composite(img)
        d = ImageDraw.Draw(bg)
        px, py = s.m_Pivot.x * img.width, img.height - s.m_Pivot.y * img.height
        d.ellipse([px - 8, py - 8, px + 8, py + 8], outline=(255, 0, 0, 255), width=3)
        d.text((6, 6), f"{n} {img.width}x{img.height}", fill=(255, 255, 0, 255))
        bg.thumbnail((520, 560))
        tiles.append(bg)
    cols = 6
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGBA", (520 * cols, 560 * rows), (40, 40, 40, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 520, (i // cols) * 560))
    sheet.thumbnail((2400, 2400))
    sheet.save(sys.argv[1])
    print("saved", sys.argv[1], sheet.size)


if __name__ == "__main__":
    main()
