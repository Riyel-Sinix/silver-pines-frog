"""Detect the original character's hands (skin blobs that are not the face) and draw them on a sheet.

usage: python -P -E hand_probe.py <out.png> <thumb_h> <Group:first-last[:step]> [...]
"""
import os
import re
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
sys.argv, ARGS = sys.argv[:1] + ["preview", "/dev/null"], sys.argv[1:]
import frogify as F  # noqa: E402
from seq_sheet import load_all  # noqa: E402
import UnityPy  # noqa: E402


def main():
    out, th = ARGS[0], int(ARGS[1])
    index = load_all()
    envs, rows = {}, []
    for spec in ARGS[2:]:
        parts = spec.split(":")
        group, (a, b) = parts[0], (int(x) for x in parts[1].split("-"))
        step = int(parts[2]) if len(parts) > 2 else 1
        tiles = []
        for i in range(a, b + 1, step):
            cands = [n for n in index if re.fullmatch(re.escape(group) + r"0*" + str(i), n)]
            if not cands:
                continue
            path, pid = index[cands[0]]
            env = envs.setdefault(path, UnityPy.load(path))
            spr = [o for o in env.objects if o.path_id == pid][0].read()
            img = spr.m_RD.texture.read().image.convert("RGBA")
            rgba = np.asarray(img)
            hands, face = F.find_hands(rgba, spr.m_PixelsToUnits)
            bg = Image.new("RGBA", img.size, (100, 100, 100, 255))
            bg.alpha_composite(img)
            d = ImageDraw.Draw(bg)
            if face is not None:
                x0, y0, x1, y1 = face
                d.rectangle([x0, y0, x1, y1], outline=(255, 0, 255, 255), width=4)
            for k, (x, y, area) in enumerate(hands):
                d.ellipse([x - 16, y - 16, x + 16, y + 16], outline=((0, 255, 0) if k == 0 else (255, 160, 0)) + (255,),
                          width=5)
            bg = bg.resize((max(1, int(img.width * th / img.height)), th), Image.LANCZOS)
            ImageDraw.Draw(bg).text((3, 3), str(i), fill=(255, 255, 0, 255))
            tiles.append(bg)
        if tiles:
            row = Image.new("RGBA", (sum(t.width + 4 for t in tiles) + 150, th), (40, 40, 40, 255))
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
