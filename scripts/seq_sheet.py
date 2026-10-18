"""Contact sheet of original player frames, one row per group (from the backed-up original bundles).

usage: python -P -E seq_sheet.py <out.png> <thumb_h> <Group:first-last[:step]> [...]
"""
import os
import re
import sys

import UnityPy
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")  # the repository
GAME = os.environ.get("SILVER_PINES", r"D:/Games/Silver Pines")  # the game folder; set SILVER_PINES if elsewhere
AA = GAME + "/Carpenter_Data/StreamingAssets/aa/StandaloneWindows64"
MAIN = ROOT + "/frogmod/backup/team17_auto_base_characters_compressed_assets_player.bundle"
if not os.path.exists(MAIN):  # mod not installed yet: the game folder still holds the original
    MAIN = AA + "/team17_auto_base_characters_compressed_assets_player.bundle"
DUMMY = "team17_auto_base_debug_compressed_assets_playercharacterdummy.bundle"


def load_all():
    found = {}
    paths = [MAIN] + [os.path.join(ROOT, "frogmod/backup/patches", f)
                      for f in os.listdir(ROOT + "/frogmod/backup/patches")]
    for p in paths:
        env = UnityPy.load(p)
        for o in env.objects:
            if o.type.name == "Sprite":
                found[o.peek_name()] = (p, o.path_id)
    return found


def main():
    out, th = sys.argv[1], int(sys.argv[2])
    specs = sys.argv[3:]
    index = load_all()
    envs = {}
    rows = []
    for spec in specs:
        parts = spec.split(":")
        group, rng = parts[0], parts[1]
        step = int(parts[2]) if len(parts) > 2 else 1
        a, b = (int(x) for x in rng.split("-"))
        tiles = []
        for i in range(a, b + 1, step):
            cands = [n for n in index if re.fullmatch(re.escape(group) + r"0*" + str(i), n)]
            if not cands:
                continue
            path, pid = index[cands[0]]
            env = envs.setdefault(path, UnityPy.load(path))
            spr = [o for o in env.objects if o.path_id == pid][0].read()
            img = spr.m_RD.texture.read().image.convert("RGBA")
            bg = Image.new("RGBA", img.size, (100, 100, 100, 255))
            bg.alpha_composite(img)
            bg = bg.resize((max(1, int(img.width * th / img.height)), th), Image.LANCZOS)
            ImageDraw.Draw(bg).text((3, 3), f"{i}", fill=(255, 255, 0, 255))
            tiles.append(bg)
        if tiles:
            row = Image.new("RGBA", (sum(t.width for t in tiles) + 4 * len(tiles) + 150, th), (40, 40, 40, 255))
            ImageDraw.Draw(row).text((4, 4), group, fill=(0, 255, 255, 255))
            x = 150
            for t in tiles:
                row.paste(t, (x, 0))
                x += t.width + 4
            rows.append(row)
    sheet = Image.new("RGBA", (max(r.width for r in rows), sum(r.height + 4 for r in rows)), (20, 20, 20, 255))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 4
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
