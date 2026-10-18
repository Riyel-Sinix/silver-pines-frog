"""Cut the laughing-frog video into sprite frames for the idle animation, plus its sound.

The video is a white-background render: each frame is cut out (white and the neutral-grey floor shadow removed,
the frog's warm cream belly kept), mirrored so the frog faces right like the game's unflipped sprites, and
cropped to one window shared by every frame so the frog moves within it as in the video. The sequence is the
laugh, the fall and roll, then the fall played backwards so the frog is standing again when idling resumes.

usage: python -P -E laugh_frames.py <video.mp4> <out_dir>
"""
import json
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from frog_parts import defringe  # noqa: E402

FPS = 12
LAUGH = (1.5, 16.5)          # seconds of the video: side view, turn, laugh, fall, roll on the floor
GET_UP = (13.25, 14.6)       # the fall, played backwards at the end
STAND_HEIGHT = 1.8           # world units: the frog's height in the first frame
AUDIO_FADE = 1.4             # seconds of fade-out over the get-up


def frames(video, t0, t1):
    w, h = 1280, 720
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}",
                          "-i", video, "-vf", f"fps={FPS},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    return [np.frombuffer(raw, np.uint8, w * h * 3, i * w * h * 3).reshape(h, w, 3) for i in range(n)]


FLOOR_SAT = 0.12             # the white floor and the grey shadows on it: unsaturated, red close to blue
FLOOR_RB = 24.0              # (the cream belly is warmer: red - blue > 30)
SHADOW_BAND = 70             # video px above the lowest point: the frog's own shadow lies on the floor in here


def border_connected(mask):
    n, lab = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    return np.isin(lab, border[border > 0])


def largest(mask):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))


def cut(rgb):
    """RGBA of the frog: the white floor and every shadow on it removed, a soft one-pixel edge.

    The floor is found by colour and kept only where it connects to the frame border, so the white teeth and
    eye highlights inside the frog stay. The shadow right under the frog is tinted by its yellow and matches
    the cream belly in colour, so near the ground (where the belly never is) any light, unsaturated pixel
    counts as floor too where it connects to the outside (the eye whites of the rolling frog are enclosed)."""
    src = rgb.astype(np.float32)
    mx, mn = src.max(axis=2), src.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    lum = src @ np.array([0.299, 0.587, 0.114], np.float32)
    floor = (sat < FLOOR_SAT) & (np.abs(src[..., 0] - src[..., 2]) < FLOOR_RB) & (lum > 50)
    rough = largest(~border_connected(floor))                # frog + the shadow under it
    bottom = int(np.nonzero(rough.any(axis=1))[0].max())
    band = np.zeros_like(floor)
    band[max(0, bottom - SHADOW_BAND):] = True
    shadow = band & (((lum > 120) & (sat < 0.30)) | ((sat < 0.15) & (lum > 50)))
    bg = border_connected(floor | shadow)
    mask = largest(~bg).astype(np.float32)                   # the frog only: drop the watermark and specks
    alpha = cv2.GaussianBlur(mask, (0, 0), 0.7) * mask       # soften the outermost ring, never grow outwards
    rgba = np.dstack([src, alpha * 255.0]).astype(np.uint8)
    return defringe(rgba, band=1)


def main():
    video, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    seq = frames(video, *LAUGH)
    get_up = frames(video, *GET_UP)[::-1]
    cuts = [cut(f)[:, ::-1] for f in seq + get_up]  # mirrored: the frog faces right
    ys, xs = np.nonzero(np.max([c[..., 3] for c in cuts], axis=0) > 20)
    x0, x1 = max(0, xs.min() - 8), min(1280, xs.max() + 9)
    y0, y1 = max(0, ys.min() - 8), min(720, ys.max() + 9)
    first = cuts[0][..., 3] > 128
    fy, fx = np.nonzero(first)
    feet = fy.max()
    foot_x = float(np.median(fx[fy > feet - 0.06 * (feet - fy.min())]))
    height = feet - fy.min() + 1
    names = []
    for i, c in enumerate(cuts):
        name = f"FrogLaugh{i:03d}"
        Image.fromarray(np.ascontiguousarray(c[y0:y1, x0:x1]), "RGBA").save(os.path.join(out, name + ".png"))
        names.append(name)
    meta = {"fps": FPS, "frames": names, "size": [int(x1 - x0), int(y1 - y0)],
            "pivot": [foot_x - x0, float(y1 - 1 - feet)],  # px from the bottom-left of the crop
            "ppu": height / STAND_HEIGHT, "laugh": LAUGH, "get_up": GET_UP}
    json.dump(meta, open(os.path.join(out, "laugh.json"), "w"), indent=1)
    dur = len(names) / FPS
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{LAUGH[0]:.3f}", "-i", video,
                    "-t", f"{dur:.3f}", "-vn", "-ac", "2", "-ar", "44100", "-af",
                    f"afade=t=out:st={dur - AUDIO_FADE:.3f}:d={AUDIO_FADE}", "-c:a", "pcm_s16le",
                    os.path.join(out, "laugh.wav")], check=True)
    print(f"{len(names)} frames ({dur:.2f}s at {FPS} fps), crop {meta['size']}, pivot {meta['pivot']}, "
          f"ppu {meta['ppu']:.1f}")


if __name__ == "__main__":
    main()
