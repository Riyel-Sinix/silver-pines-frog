"""Frog-only showcase sheet: one labelled row per feature, frames standing on a common baseline.

usage: python -P -E showcase.py <out.png> "label|Name,Name,..." ["label|..." ...]
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
sys.argv, ARGS = sys.argv[:1] + ["preview", "/dev/null"], sys.argv[1:]
import frogify as F  # noqa: E402
import UnityPy  # noqa: E402

ROW_H = 300          # px per row (frames are scaled so 1 world unit = ROW_H / 2.6 px)
LABEL_W = 260
FONT = r"C:/Windows/Fonts/msyh.ttc"


def render(names):
    pidx = F.patch_index()
    main_env = UnityPy.load(F.ORIG_MAIN)
    main_names = [o.read().m_Name for o in main_env.objects if o.type.name == "Sprite"]
    counts = F.group_counts(main_names, pidx)
    F.measure_rest(main_env)
    patch_fns = F.player_patch_bundles(pidx)
    feet = {}
    F.collect_feet(main_env, counts, feet)
    for fn in patch_fns:
        F.collect_feet(UnityPy.load(F.source_bundle(fn)), counts, feet)
    F.plan_legs(feet)
    stats, previews = F.new_stats(), []
    want = set(names)
    F.process_env(main_env, counts, stats, only=want, previews=previews)
    for fn in patch_fns:
        listed = set(pidx.get(fn, [])) if fn in pidx else None
        if listed is None or want & listed:
            F.process_env(UnityPy.load(F.source_bundle(fn)), counts, stats, only=want, previews=previews)
    return {p[0]: p for p in previews}


def main():
    out = ARGS[0]
    rows = [(spec.split("|")[0], spec.split("|")[1].split(",")) for spec in ARGS[1:]]
    by = render([n for _, names in rows for n in names])
    font = ImageFont.truetype(FONT, 34)
    unit = ROW_H / 2.6
    strips = []
    for label, names in rows:
        cells = []
        for n in names:
            if n not in by or by[n][3] is None:
                continue
            _, _, new, info, _ = by[n]
            k = unit / info["ppu"]
            im = new.resize((max(1, int(new.width * k)), max(1, int(new.height * k))), Image.LANCZOS)
            cells.append((im, info["p2x"] * k, info["p2y"] * k))
        if not cells:
            continue
        base = int(max(im.height - py for im, _, py in cells)) + 10   # pivots on one baseline
        row_h = max(ROW_H, base + int(max(py for _, _, py in cells)) + 10)
        width = LABEL_W + int(sum(im.width * 0.8 for im, _, _ in cells)) + 80
        strip = Image.new("RGBA", (width, row_h), (58, 58, 64, 255))
        d = ImageDraw.Draw(strip)
        d.text((16, row_h // 2 - 22), label, font=font, fill=(255, 225, 120, 255))
        d.line([(LABEL_W - 10, base), (width, base)], fill=(90, 90, 98, 255), width=2)
        x = LABEL_W
        for im, px, py in cells:
            strip.alpha_composite(im, (int(x), int(base - (im.height - py))))
            x += im.width * 0.8
        strips.append(strip)
    sheet = Image.new("RGBA", (max(s.width for s in strips), sum(s.height + 6 for s in strips)), (30, 30, 34, 255))
    y = 0
    for s in strips:
        sheet.paste(s, (0, y))
        y += s.height + 6
    sheet.thumbnail((2600, 2600))
    sheet.convert("RGB").save(out, quality=92)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
