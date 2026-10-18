"""Cut a character out of a plain white background (border flood fill + soft, colour-decontaminated edges).

usage: python -P -E cutout.py <in.png> <out.png> [preview.png]
"""
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter


def main():
    src = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(np.float32)
    h, w, _ = src.shape
    # distance from pure white
    dist = np.sqrt(((255.0 - src) ** 2).sum(axis=2))
    bgish = dist < 60.0
    # background = near-white pixels connected to the image border
    bg = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bgish[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if bgish[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and bgish[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True
                q.append((ny, nx))
    # enclosed holes (e.g. between the legs) and the grey floor shadow: low-saturation bright regions
    mx, mn = src.max(axis=2), src.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    greyish = (sat < 0.16) & (mx > 140.0)
    seen = np.zeros((h, w), bool)
    for sy in range(h):
        for sx in range(w):
            if not greyish[sy, sx] or seen[sy, sx]:
                continue
            comp = [(sy, sx)]
            seen[sy, sx] = True
            q = deque(comp)
            while q:
                y, x = q.popleft()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and greyish[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        comp.append((ny, nx))
                        q.append((ny, nx))
            touches_bg = any(bg[y, x] or y in (0, h - 1) or x in (0, w - 1) for y, x in comp)
            low = np.mean([y for y, _ in comp]) > 0.55 * h
            if touches_bg or (len(comp) > 60 and low):
                for y, x in comp:
                    bg[y, x] = True
    # soft alpha: background pixels close to the subject get partial alpha from their distance to white
    alpha = np.where(bg, np.clip((dist - 12.0) / 48.0, 0.0, 1.0), 1.0)
    near = np.asarray(Image.fromarray((~bg).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
    alpha = np.where(bg & ~near, 0.0, alpha)
    alpha = np.where(bg & greyish, alpha * 0.2, alpha)  # floor-shadow fringe
    # remove white spill: c = a*fg + (1-a)*255  ->  fg = (c - (1-a)*255) / a
    a3 = np.maximum(alpha[..., None], 1e-3)
    fg = np.clip((src - (1.0 - a3) * 255.0) / a3, 0, 255)
    rgba = np.dstack([fg, alpha * 255.0]).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA")
    img = img.crop(img.getbbox())
    img.save(sys.argv[2])
    print("saved", sys.argv[2], img.size)
    if len(sys.argv) > 3:
        prev = Image.new("RGBA", (img.width * 3 + 40, img.height + 20), (60, 60, 60, 255))
        for i, col in enumerate([(60, 60, 60, 255), (200, 40, 160, 255), (20, 20, 20, 255)]):
            tile = Image.new("RGBA", img.size, col)
            tile.alpha_composite(img)
            prev.paste(tile, (10 + i * (img.width + 10), 10))
        prev = prev.resize((prev.width * 2, prev.height * 2), Image.NEAREST)
        prev.save(sys.argv[3])


if __name__ == "__main__":
    main()
