"""Silver Pines: replace the player character with the frog (奶蛙), v2.

- body frames: frog drawn from the original frame's silhouette (position, height, lean, lying); its two legs
  are sheared about the hip to follow the original character's feet, so walking steps instead of sliding;
- weapon poses whose arms come from separate overlay sprites use an arm-less frog body;
- arm overlays are recoloured to frog colours (sleeve yellow, hand olive), the rifle-draw overlay loses its head;
- the separate aiming head is hidden; weapons and effects are untouched;
- tight sprite meshes of redrawn frames become full-rect quads (canvas grows when needed, pivot kept in place).

usage:
  python -P -E frogify.py main <out.bundle>                 # original main bundle (frogmod/backup, else the game)
  python -P -E frogify.py patches <out_dir>                  # every other bundle that holds player sprites
  python -P -E frogify.py preview <sheet.png> <name> [...]   # original | frog side by side, nothing written
  python -P -E frogify.py strip <strip.png> <name> [...]     # frog over a ghost of the original, pivots aligned
"""
import json
import math
import os
import re
import struct
import sys

import cv2
import numpy as np
import UnityPy
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from UnityPy.enums import TextureFormat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")  # the repository
GAME = os.environ.get("SILVER_PINES", r"D:/Games/Silver Pines")  # the game folder; set SILVER_PINES if elsewhere
AA = GAME + "/Carpenter_Data/StreamingAssets/aa/StandaloneWindows64"
MAIN = "team17_auto_base_characters_compressed_assets_player.bundle"
ORIG_MAIN = ROOT + "/frogmod/backup/" + MAIN
if not os.path.exists(ORIG_MAIN):  # mod not installed yet: the game folder still holds the original
    ORIG_MAIN = AA + "/" + MAIN
PATCH_INDEX = ROOT + "/_dump/patch_bundle_sprites.txt"
PARTS_DIR = ROOT + "/frogmod/parts"
BACKUP_PATCHES = ROOT + "/frogmod/backup/patches"

FROG_HEIGHT = 1.80      # world units, same as the original character so overlay arms meet the shoulders
STAND_HEIGHT = 1.80
ALPHA_CUT = 40
LEG_K = 1.0             # frog foot travel per unit of the original foot travel (1 = feet land where his do)
CROSS_SEP = 0.12        # feet closer than this (world units) count as passing each other
FROG_YELLOW = np.array([236.0, 190.0, 52.0])
FROG_HAND = np.array([112.0, 98.0, 46.0])

# The groups below follow the game's AnimationClips (_dump/clip_map.txt): aiming draws an arm-less body plus
# code-driven arm sprites; reload / rifle-draw / blocked-rifle clips pair a body clip with an "Arm Sprite" clip.
OVERLAY_GROUPS = {   # arm sprites drawn on top of an arm-less frog: recoloured
    "PlayerArmAimBack", "PlayerArm", "arm_rifle_front", "arm_rifle_back", "arm_SMG_back", "PlayerAimArm",
    "arm_Shotgun_Lever_front_", "PlayerReloadBoltActionArm", "PlayerThrowArmFront", "PlayerThrowArmBack",
    "PlayerReloadArms", "PlayerCrouchReloadArms", "PlayerReloadShotgunArm", "PlayerRifleDrawArms",
    "PlayerAimBlockedRifle_arms",
}
ARMLESS_GROUPS = {   # body frames shown together with overlay arms
    "PlayerAimArcNoarms", "PlayerAimWalk", "PlayerCrouchAim", "player_anim_aim_body", "PlayerReload",
    "PlayerCrouchReload", "PlayerReloadShotgun", "PlayerRifleDraw", "PlayerAimBlockedRifle", "PlayerReloadBoltAction",
}
# hidden: the old aiming head, and overlays that would add a third arm to bodies that draw their own arms
HIDE_GROUPS = {"player_aim_head", "PlayerDrawGunArm", "PlayerRifleTurnArms", "PlayerAimShotgunPumpArm"}
EXTRA_BODY_GROUPS = {"player_anim_aim_body", "player_walk"}
SKIP_GROUPS = {"Player_difficuly_inquisitive", "Player_difficuly_upset", "PlayerCarHeadlight01Cookie"}
EXTRA_BUNDLES = ["team17_auto_base_debug_compressed_assets_playercharacterdummy.bundle"]  # throwing arms

PARTS = {}  # layer name -> bled RGBA image, loaded on first use
META = json.load(open(f"{PARTS_DIR}/parts.json"))
P_W, P_H = META["size"]
P_HIP_Y, P_HIP_X = META["hip_y"], META["hip_x"]
REST = [0.28, -0.13]  # original character's idle foot offsets (forward, world units); measured in main()
FROG_REST = ((P_HIP_X - META["front_foot_x"]) / P_W, (P_HIP_X - META["back_foot_x"]) / P_W)  # x frog width
LEGS = {}  # sprite name -> (near foot, near lift, far foot, far lift), world units from the hip, forward +


def group_of(name):
    return re.sub(r"\d+(_flipped)?$", "", name)


def frame_index(name):
    m = re.search(r"(\d+)(_flipped)?$", name)
    return int(m.group(1)) if m else 0


def classify(group):
    if group in HIDE_GROUPS:
        return "hide"
    if group in OVERLAY_GROUPS:
        return "overlay"
    if group in SKIP_GROUPS:
        return "skip"
    if group in EXTRA_BODY_GROUPS or group.startswith("Player"):
        return "body"
    return "skip"


# ---------------------------------------------------------------- image helpers
# Resampling works on straight alpha over colour-bled images: premultiplied LANCZOS rings at hard alpha edges,
# and un-premultiplying the tiny ringing alphas turns them into white specks around the frog.
def part(name):
    if name not in PARTS:
        PARTS[name] = bleed(Image.open(f"{PARTS_DIR}/{name}.png").convert("RGBA"))
    return PARTS[name]


def resize_rgba(img, size):
    return img.resize(size, Image.LANCZOS)


def rotate_rgba(img, angle):
    return bleed(img).rotate(angle, resample=Image.BICUBIC, expand=True)


def bleed(img):
    """Spread edge colours into fully transparent pixels so bilinear filtering does not darken edges."""
    a = np.asarray(img).astype(np.float32)
    alpha = a[..., 3:4] / 255.0
    pm = Image.fromarray(np.clip(a[..., :3] * alpha, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(3))
    al = Image.fromarray((alpha[..., 0] * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(3))
    bpm = np.asarray(pm).astype(np.float32)
    bal = np.asarray(al).astype(np.float32)[..., None] / 255.0
    spread = np.where(bal > 1e-3, bpm / np.maximum(bal, 1e-3), 0)
    rgb = np.where(alpha > 0, a[..., :3], np.clip(spread, 0, 255))
    return Image.fromarray(np.dstack([rgb, a[..., 3]]).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- analysis of the original frame
def silhouette(alpha):
    ys, xs = np.nonzero(alpha > ALPHA_CUT)
    if len(xs) < 80:
        return None
    h = alpha.shape[0]
    yb = h - 1 - ys
    cx, cy = xs.mean(), yb.mean()
    cov = np.cov(np.vstack([xs - cx, yb - cy]))
    evals, evecs = np.linalg.eigh(cov)
    major = evecs[:, np.argmax(evals)]
    if major[1] < 0:
        major = -major
    proj = (xs - cx) * major[0] + (yb - cy) * major[1]
    return {"x0": xs.min(), "x1": xs.max() + 1, "y0": yb.min(), "y1": yb.max() + 1, "cx": cx, "cy": cy,
            "lean": math.degrees(math.atan2(major[0], major[1])),
            "elong": math.sqrt(max(evals.max(), 1e-6) / max(evals.min(), 1e-6)),
            "major_len": float(proj.max() - proj.min())}


def foot_info(alpha, sil, face_left):
    """Forward offsets of the front/back foot from the torso centre and their lift, in frame pixels."""
    hh = alpha.shape[0]
    height = sil["y1"] - sil["y0"]
    rb = hh - 1 - sil["y0"]
    rt = max(0, int(hh - 1 - (sil["y0"] + 0.16 * height)))
    band = alpha[rt:rb + 1] > ALPHA_CUT
    colsum = band.sum(axis=0)
    xs = np.nonzero(colsum)[0]
    if len(xs) == 0:
        return None
    runs = np.split(xs, np.nonzero(np.diff(xs) > 4)[0] + 1)
    total = colsum.sum()
    sig = [r for r in runs if colsum[r].sum() >= 0.08 * total]
    if not sig:
        return None
    t0 = max(0, int(hh - 1 - (sil["y0"] + 0.75 * height)))
    t1 = int(hh - 1 - (sil["y0"] + 0.45 * height))
    txs = np.nonzero(alpha[t0:t1 + 1] > ALPHA_CUT)[1]
    hip_x = float(txs.mean()) if len(txs) else float(sil["cx"])

    def center(r):
        return float((r * colsum[r]).sum() / colsum[r].sum())

    def bottom(r):
        rows = np.nonzero(band[:, r[0]:r[-1] + 1].any(axis=1))[0]
        return hh - 1 - (rt + rows.max())

    left, right = sig[0], sig[-1]
    front, back = (left, right) if face_left else (right, left)
    fwd = (lambda x: hip_x - x) if face_left else (lambda x: x - hip_x)
    g = min(bottom(front), bottom(back))
    return {"hip_x": hip_x, "two": len(sig) >= 2, "front": fwd(center(front)), "back": fwd(center(back)),
            "lift_front": bottom(front) - g, "lift_back": bottom(back) - g}


# ---------------------------------------------------------------- frog rendering
def shear_leg(leg, shift, lift, hip, pad, width, slide=0.0):
    """Shear a leg layer about the hip line: the foot moves `shift` px sideways and `lift` px up; `slide` moves the
    whole leg (its top too) sideways."""
    h = leg.height
    length = h - hip
    lift = min(max(lift, 0.0), 0.45 * length)
    lp = length - lift
    e = length / lp
    f = hip - hip * e
    b = -shift / lp
    c = -pad + shift * hip / lp - slide
    return leg.transform((width, h), Image.AFFINE, (1, b, c, 0, e, f), resample=Image.BICUBIC)


FAR_LEG_SHADE = 0.8   # the far leg is the near leg's profile, darker
SIDE_TOPS = []        # cut-out x of the near / far side leg's top (the hip-line centre)


def side_legs():
    """(near, far) side-view leg layers. The cut-out's back leg is drawn in 3/4 view (a stubby foot), so both are its
    profile front leg, cleaned of the ground shadow and the light streak under the sole and of the stray toes of
    the other foot; the far one is shaded and stands where the back leg stood."""
    if "side_near" not in PARTS:
        src = np.asarray(Image.open(f"{PARTS_DIR}/leg_front.png").convert("RGBA")).astype(np.float32)
        rgb, a = src[..., :3], src[..., 3]
        lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
        mx, mn = rgb.max(axis=2), rgb.min(axis=2)
        sat = (mx - mn) / np.maximum(mx, 1.0)
        streak = ((lum > 160) & (sat < 0.25)) | ((a < 200) & (lum > 100) & (sat < 0.35))  # cream, and its soft edge
        n, lab, st, _ = cv2.connectedComponentsWithStats(((a > 128) & ~streak).astype(np.uint8))
        main = (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
        a = np.where((cv2.dilate(main, np.ones((3, 3), np.uint8)) > 0) & ~streak, a, 0)
        for x in range(a.shape[1]):  # the soft edge under the sole takes the sole's colour, not the ground's
            ys = np.nonzero(a[:, x] > 128)[0]
            if len(ys):
                rgb[ys.max() + 1:, x] = rgb[ys.max(), x]
        near = Image.fromarray(np.dstack([rgb, a]).astype(np.uint8), "RGBA")
        dx = META["back_foot_x"] - META["front_foot_x"]
        far = Image.fromarray(np.dstack([np.clip(rgb * FAR_LEG_SHADE, 0, 255), a]).astype(np.uint8), "RGBA")
        far = bleed(far).transform(far.size, Image.AFFINE, (1, 0, -dx, 0, 1, 0), resample=Image.BICUBIC)
        PARTS["side_near"], PARTS["side_far"] = bleed(near), bleed(far)
        for im in (PARTS["side_near"], PARTS["side_far"]):
            xs = np.nonzero(np.asarray(im)[P_HIP_Y:P_HIP_Y + 8, :, 3] > 128)[1]
            SIDE_TOPS.append(float(xs.mean()))
    return PARTS["side_near"], PARTS["side_far"]


def leg_slides(legs, w, face_left):
    """Screen-px slides of the near / far leg tops. At rest each leg hangs from its own side of the belly; as the
    feet come together the tops meet under the hip, and once the near foot is behind the far one the tops trade
    places, so the legs hinge like a side view and never cross in an X."""
    sgn = -1.0 if face_left else 1.0
    side_legs()
    fn, ff = ((P_HIP_X - x) * w / P_W for x in SIDE_TOPS)  # forward offsets of the tops (the cut-out faces left)
    mid = 0.5 * (fn + ff)
    rest_n, rest_f = FROG_REST[0] * w, FROG_REST[1] * w
    d = (rest_n + sgn * legs[0]) - (rest_f + sgn * legs[2])
    keep = max(-1.0, min(1.0, d / (rest_n - rest_f)))
    return sgn * (keep - 1.0) * (fn - mid), sgn * (keep - 1.0) * (ff - mid), keep


BODY_ROUND = (54.0, 100.0, 44.9, 47.0, 130)  # cut-out ellipse (cx, cy, rx, ry) for the belly's underside below row 130
BODY_HW = {}


def body_halfwidths(variant):
    """Half-width (cut-out px, about BODY_ROUND's centre) of the opaque body per cut-out row."""
    if variant not in BODY_HW:
        a = np.asarray(part("body_" + variant))[..., 3] > 128
        cx, hw, last = BODY_ROUND[0], [], 0.0
        for y in range(P_H):
            xs = np.nonzero(a[y])[0]
            last = max(cx - xs.min(), xs.max() - cx) + 1.0 if len(xs) else last
            hw.append(last)
        BODY_HW[variant] = np.array(hw)
    return BODY_HW[variant]


def round_bottom(body, variant, w, h, face_left, r):
    """The body layer is cut flat where the legs start; when the legs move in under the hip that cut shows, so
    narrow the underside towards an ellipse by r (0 = as cut, 1 = fully round)."""
    if r <= 0.02:
        return body
    cx, cy, rx, ry, y_start = BODY_ROUND
    sx, sy = w / P_W, h / P_H
    a = np.asarray(body).astype(np.float32)
    rows = np.arange(int(y_start * sy), h)
    yc = rows / sy
    hw_e = rx * np.sqrt(np.clip(1.0 - ((yc - cy) / ry) ** 2, 0.0, 1.0))
    hw_b = body_halfwidths(variant)[np.clip(yc.astype(int), 0, P_H - 1)]
    hw = (hw_e + (1.0 - r) * np.maximum(hw_b - hw_e, 0.0)) * sx
    x_c = (cx if face_left else P_W - cx) * sx
    m = np.clip(hw[:, None] - np.abs(np.arange(w)[None, :] + 0.5 - x_c) + 0.5, 0.0, 1.0)
    a[rows[0]:, :, 3] *= m
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def render_frog(variant, w, h, face_left, legs=None, tilt=0.0):
    """Returns (image, pad). `legs` = (near shift, near lift, far shift, far lift) in screen px; `tilt` leans the
    body (not the legs) by shearing it about the hip line, top towards +x for positive degrees."""
    def prep(im):
        return resize_rgba(im if face_left else ImageOps.mirror(im), (w, h))  # the source faces left
    body = prep(part("body_" + variant))
    lf, lb = (prep(im) for im in side_legs())
    legs = legs or (0.0, 0.0, 0.0, 0.0)
    hip = P_HIP_Y * h / P_H
    k = math.tan(math.radians(tilt))
    margin = int(math.ceil(abs(k) * hip)) + 2 if tilt else 0
    pad = int(math.ceil(max(abs(legs[0]), abs(legs[2])))) + 2 + margin
    width = w + 2 * pad
    canvas = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    sn, sf, keep = leg_slides(legs, w, face_left)
    body = round_bottom(body, variant, w, h, face_left, 1.0 - abs(keep))
    canvas.alpha_composite(shear_leg(lb, legs[2] - sf, legs[3], hip, pad, width, sf))
    canvas.alpha_composite(shear_leg(lf, legs[0] - sn, legs[1], hip, pad, width, sn))
    if tilt:
        layer = Image.new("RGBA", (width, h), (0, 0, 0, 0))
        layer.paste(body, (pad, 0))
        layer = bleed(layer).transform((width, h), Image.AFFINE, (1, k, -k * hip, 0, 1, 0), resample=Image.BICUBIC)
        canvas.alpha_composite(layer)
    else:
        canvas.alpha_composite(body, (pad, 0))
    return canvas, pad


def frog_hip_x(w, face_left):
    return (P_HIP_X if face_left else P_W - P_HIP_X) * w / P_W


def soft_limit(v, lim):
    """Linear up to 70% of lim, then eases into lim."""
    knee = 0.7 * lim
    if abs(v) <= knee:
        return v
    return math.copysign(knee + (lim - knee) * math.tanh((abs(v) - knee) / (lim - knee)), v)


def leg_shifts(plan, w, h, ppu, face_left):
    """Screen-pixel (near shift, near lift, far shift, far lift) for render_frog from a LEGS plan."""
    if plan is None:
        return None
    lim = 0.75 * h * (P_H - P_HIP_Y) / P_H
    rest = (FROG_REST[0] * w, FROG_REST[1] * w)
    center = (rest[0] + rest[1]) / 2.0
    human_c = (REST[0] + REST[1]) / 2.0
    sign = -1.0 if face_left else 1.0
    near = center + soft_limit(LEG_K * (plan[0] - human_c) * ppu, lim)
    far = center + soft_limit(LEG_K * (plan[2] - human_c) * ppu, lim)
    return sign * (near - rest[0]), LEG_K * plan[1] * ppu, sign * (far - rest[1]), LEG_K * plan[3] * ppu


UPRIGHT_LEAN = 35.0                      # beyond this lean (and elongated) the whole frog is rotated
TILT_MIN, TILT_GAIN, TILT_MAX = 8.0, 0.7, 22.0  # smaller leans tilt only the frog's body


def upright(sil):
    return abs(sil["lean"]) < UPRIGHT_LEAN or sil["elong"] < 1.5


def body_tilt(lean):
    return 0.0 if abs(lean) < TILT_MIN else max(-TILT_MAX, min(TILT_MAX, lean * TILT_GAIN))


def body_scale(ratio):
    """(sx, sy) of the frog from the original silhouette's height ratio: squash when low, stretch when tall."""
    if ratio < 0.86:
        sy = max(ratio / 0.9, 0.58)
        return 1.0 + (1.0 - sy) * 0.55, sy
    if ratio > 1.08:
        sy = min(ratio, 1.3)
        return 1.0 / math.sqrt(sy), sy
    sy = min(max(ratio / 0.97, 0.97), 1.03)
    return 1.0 / math.sqrt(sy), sy


def plan_body(rgba, ppu, pivot, face_left, group, name):
    """Returns the frog's layers [(image, left, bottom), ...] back to front, in original-canvas pixels
    (bottom-left origin), or None."""
    rgb, alpha = rgba[..., :3].astype(np.float32), rgba[..., 3]
    sil = silhouette(alpha)
    if sil is None:
        return None
    view = view_of(group, name, rgba, sil)
    if view in ("front", "back") and upright(sil):
        return plan_view(view, group, name, alpha, sil, ppu)
    variant = "glance" if view == "glance" else ("noarms" if group in ARMLESS_GROUPS else "arms")
    fh = FROG_HEIGHT * ppu
    fw = fh * P_W / P_H
    hs = (sil["y1"] - sil["y0"]) / ppu
    lean = sil["lean"]
    rope = rope_hands(rgba, ppu) if group in ROPE_GROUPS else None
    hang = hang_target(alpha, sil, ppu) if group in HANG_GROUPS and rope is None else None
    if upright(sil) or hang is not None or rope is not None:
        mode = "rope" if rope is not None else ("hang" if hang is not None else arm_mode(group, name))
        if mode is not None:
            variant = "noarms"
        held = mode in ("hang", "rope")  # hanging from the hands: normal size, legs dangling
        sx, sy = body_scale(hs / STAND_HEIGHT) if not held else (1.0, 1.0)
        w, h = max(8, int(round(fw * sx))), max(8, int(round(fh * sy)))
        fi = foot_info(alpha, sil, face_left)
        hip_x = fi["hip_x"] if fi is not None else sil["cx"]
        tilt = body_tilt(lean)
        legs = leg_shifts(LEGS.get(name), w, h, ppu, face_left) if not held else None
        img, pad = render_frog(variant, w, h, face_left, legs, tilt)
        bottom = sil["y1"] - h if hs / STAND_HEIGHT > 1.12 else sil["y0"]
        shoulder_h = (P_H - NEAR_SHOULDER[1]) * h / P_H
        if mode == "hang":  # hands on the grip, body hanging below it; never lower than his feet
            reach = HANG_REACH * (ARM_LEN[0] + ARM_LEN[1]) * h / P_H
            bottom = max(sil["y0"], hang[1] - shoulder_h - reach)
            hip_x = 0.5 * (hip_x + hang[0])
        left = hip_x - (pad + frog_hip_x(w, face_left))
        if mode == "rope":  # shoulders just below the lower hand, belly just behind the rope
            lower = rope[1]
            bottom = lower[1] - ROPE_DROP * h - shoulder_h
            front = pad + (FROG_FRONT if face_left else P_W - FROG_FRONT) * w / P_W
            left = lower[0] - (-1.0 if face_left else 1.0) * ROPE_GAP * w - front
        if mode is None:
            return [(img, left, bottom)]
        frame = {"w": w, "h": h, "pad": pad, "left": left, "bottom": bottom, "tilt": tilt, "ppu": ppu,
                 "face_left": face_left, "pivot": pivot, "hang": hang, "rope": rope}
        far, near = plan_arms(mode, group, name, frame)
        return [layer for layer in (far, (img, left, bottom), near) if layer is not None]
    # lying / diving / crawling: rotate the whole frog so its head points where his head is
    d = np.array([math.sin(math.radians(lean)), math.cos(math.radians(lean))])  # major axis, upward half
    head_sign = head_direction(rgb, alpha, sil, d)
    if group in SWIM_GROUPS:  # a swimmer's head leads, whatever his hands show mid-stroke
        head_sign = 1.0 if d[0] * (-1.0 if face_left else 1.0) >= 0 else -1.0
    if head_sign is None:
        head_sign = 1.0 if abs(lean) <= 70 else (1.0 if (sil["cx"] > pivot[0]) == (d[0] > 0) else -1.0)
    d = d * head_sign
    angle = math.degrees(math.atan2(d[0], d[1]))
    length = min(max(sil["major_len"] / ppu, 0.72 * FROG_HEIGHT), 1.05 * FROG_HEIGHT) * ppu
    stroke = SWIM_GROUPS.get(group)
    w0, h0 = max(8, int(round(length * P_W / P_H))), max(8, int(round(length)))
    img0, pad0 = render_frog("noarms" if stroke else variant, w0, h0, face_left)
    img = rotate_rgba(img0, -angle)
    left = sil["cx"] - img.width / 2.0
    bottom = max(sil["y0"], sil["cy"] - img.height / 2.0)
    if not stroke:
        return [(img, left, bottom)]
    frame = {"w": w0, "h": h0, "pad": pad0, "tilt": 0.0, "face_left": face_left, "ppu": ppu,
             "rot": (img0.size, img.size, -angle), "left": left, "bottom": bottom, "head_dir": d}
    far, near = plan_swim_arms(stroke, name, frame)
    return [far, (img, left, bottom), near]


# ---------------------------------------------------------------- views: front / back / glance
VIEWS = {}
BACK_GROUPS = {"PlayerEnterIntoFrontDoor", "PlayerStairsDownInward", "PlayerLadderClimb"}
BACK_PROBE_GROUPS = {"PlayerLadderEnter", "PlayerLadderExit"}         # back view while no face shows
FRONT_GROUPS = {"PlayerWalkToCamera", "PlayerEnterThroughDoorFront", "PlayerTurn"}
FRONT_PROBE_GROUPS = {"PlayerWalkToCameraEnd", "PlayerStairsTurn", "PlayerCrouchTurn", "PlayerRunTurn"}
GLANCE_PROBE_GROUPS = {"PlayerIdleLook"}                              # looking at the camera -> 惊鸿一瞥
GLANCE_FRAMES = {"PlayerIdle_v2_loop": {5, 6}}                        # a glance in every standing idle loop
CLIMB_GROUPS = {"PlayerLadderClimb", "PlayerLadderEnter", "PlayerLadderExit"}  # back view, arms up the ladder
FACE_BACK, FACE_FRONT = 0.2, 0.38                                     # face skin fraction thresholds


def views():
    if not VIEWS:
        VIEWS.update(json.load(open(f"{PARTS_DIR}/views.json")))
    return VIEWS


def face_fraction(rgba, sil):
    """Skin share of the head (hair + skin) in the top 15% of an upright silhouette: ~0 back, ~0.27 side,
    >0.4 when he faces the camera."""
    rgb = rgba[..., :3].astype(np.float32)
    a = rgba[..., 3]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    top = a.shape[0] - 1 - sil["y1"]
    rows = slice(max(0, int(top)), int(top + 0.15 * (sil["y1"] - sil["y0"])))
    op = a[rows] > 200
    hair = (op & (lum[rows] < 45)).sum()
    skin = (op & skin_mask(rgb[rows], lum[rows])).sum()
    return skin / max(1, skin + hair)


def view_of(group, name, rgba, sil):
    if group in GLANCE_FRAMES:
        return "glance" if frame_index(name) in GLANCE_FRAMES[group] else "side"
    if group in BACK_GROUPS:
        return "back"
    if group in FRONT_GROUPS:
        return "front"
    if group in BACK_PROBE_GROUPS | FRONT_PROBE_GROUPS | GLANCE_PROBE_GROUPS:
        f = face_fraction(rgba, sil)
        if group in BACK_PROBE_GROUPS and f < FACE_BACK:
            return "back"
        if group in FRONT_PROBE_GROUPS and f >= FACE_FRONT:
            return "front"
        if group in GLANCE_PROBE_GROUPS and f >= FACE_FRONT:
            return "glance"
    return "side"


def feet_lr(alpha, sil):
    """(left, right) foot lift in px for front / back views: the outer foot runs' bottoms."""
    hh = alpha.shape[0]
    height = sil["y1"] - sil["y0"]
    rb = hh - 1 - sil["y0"]
    rt = max(0, int(hh - 1 - (sil["y0"] + 0.2 * height)))
    band = alpha[rt:rb + 1] > ALPHA_CUT
    colsum = band.sum(axis=0)
    xs = np.nonzero(colsum)[0]
    if len(xs) == 0:
        return 0.0, 0.0
    runs = np.split(xs, np.nonzero(np.diff(xs) > 4)[0] + 1)
    sig = [r for r in runs if colsum[r].sum() >= 0.08 * colsum.sum()]
    if len(sig) < 2:
        return 0.0, 0.0

    def bottom(r):
        rows = np.nonzero(band[:, r[0]:r[-1] + 1].any(axis=1))[0]
        return hh - 1 - (rt + rows.max())

    bl, br = bottom(sig[0]), bottom(sig[-1])
    g = min(bl, br)
    return float(bl - g), float(br - g)


def torso_x(alpha, sil):
    hh = alpha.shape[0]
    height = sil["y1"] - sil["y0"]
    t0 = max(0, int(hh - 1 - (sil["y0"] + 0.75 * height)))
    t1 = int(hh - 1 - (sil["y0"] + 0.45 * height))
    xs = np.nonzero(alpha[t0:t1 + 1] > ALPHA_CUT)[1]
    return float(np.median(xs)) if len(xs) else float(sil["cx"])


def render_view(view, body, w, h, lifts):
    """Front / back frog: body layer over two legs that shorten with each foot's lift."""
    meta = views()[view]
    hip = meta["hip_y"] * h / meta["size"][1]
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for side, lift in (("l", lifts[0]), ("r", lifts[1])):
        canvas.alpha_composite(shear_leg(resize_rgba(part(f"{view}_leg_{side}"), (w, h)), 0.0, lift, hip, 0, w))
    canvas.alpha_composite(resize_rgba(part(f"{view}_{body}"), (w, h)))
    return canvas


def plan_view(view, group, name, alpha, sil, ppu):
    meta = views()[view]
    vw, vh = meta["size"]
    climb = view == "back" and group in CLIMB_GROUPS
    ratio = (sil["y1"] - sil["y0"]) / ppu / STAND_HEIGHT
    sx, sy = body_scale(ratio) if not climb else (1.0, 1.0)
    h = max(8, int(round(FROG_HEIGHT * ppu * sy)))
    w = max(8, int(round(FROG_HEIGHT * ppu * vw / vh * sx)))
    lifts = feet_lr(alpha, sil)
    img = render_view(view, "body_noarms" if climb else "body", w, h, lifts)
    left = torso_x(alpha, sil) - w / 2.0
    bottom = sil["y1"] - h if ratio > 1.12 and not climb else sil["y0"]
    if not climb:
        return [(img, left, bottom)]
    # ladder: the hand opposite the higher foot reaches for the next rung
    sc = h / P_H
    l1, l2 = ARM_LEN[0] * sc, ARM_LEN[1] * sc
    top = bottom + h
    high_left = lifts[1] > lifts[0] + 2
    high_right = lifts[0] > lifts[1] + 2
    arms = []
    for k, (sxp, syp) in enumerate(meta["shoulders"]):
        s = (left + sxp * w / vw, bottom + h - syp * h / vh)
        inward = 1.0 if k == 0 else -1.0
        high = high_left if k == 0 else high_right
        hy = top + (0.12 if high else (0.02 if not (high_left or high_right) else -0.06)) * h
        e, hand = solve_elbow(s, (s[0] + inward * 0.04 * w, hy), l1, l2, inward)  # elbows point outward
        arms.append(draw_arm(s, e, hand, sc))
    return [(img, left, bottom)] + arms


def head_direction(rgb, alpha, sil, d):
    """+1 if the head is at the +d end of the silhouette, -1 if at the other end, None if unclear.
    The face and hands are the only skin-coloured pixels and sit at the head end when lying or crawling."""
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    skin = skin_mask(rgb, lum) & (alpha > 200)
    ys, xs = np.nonzero(skin)
    if len(xs) < 40:
        return None
    h = alpha.shape[0]
    proj = (xs - sil["cx"]) * d[0] + ((h - 1 - ys) - sil["cy"]) * d[1]
    m = float(np.median(proj))
    if abs(m) < 0.08 * sil["major_len"]:
        return None
    return 1.0 if m > 0 else -1.0


def face_left_of(name, group, counts):
    count = counts.get(group, 1)
    return "flipped" in name or ("Turn" in group and count > 1 and frame_index(name) >= count / 2.0)


def render_body(tree, img, group, name, counts):
    w, h = img.size
    ppu = tree["m_PixelsToUnits"]
    px, py = tree["m_Pivot"]["x"] * w, tree["m_Pivot"]["y"] * h
    layers = plan_body(np.asarray(img), ppu, (px, py), face_left_of(name, group, counts), group, name)
    if layers is None:
        return None
    x_min = min([0.0] + [math.floor(lft) - 2 for _, lft, _ in layers])
    y_min = min([0.0] + [math.floor(btm) - 2 for _, _, btm in layers])
    x_max = max([float(w)] + [math.ceil(lft + im.width) + 2 for im, lft, _ in layers])
    y_max = max([float(h)] + [math.ceil(btm + im.height) + 2 for im, _, btm in layers])
    w2 = int(math.ceil((x_max - x_min) / 4.0) * 4)
    h2 = int(math.ceil((y_max - y_min) / 4.0) * 4)
    ox, oy = -x_min, -y_min
    canvas = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    for im, lft, btm in layers:
        canvas.alpha_composite(im, (int(round(lft + ox)), h2 - int(round(btm + oy)) - im.height))
    return bleed(canvas), {"w2": w2, "h2": h2, "p2x": px + ox, "p2y": py + oy, "ppu": ppu, "ox": ox, "oy": oy}


# ---------------------------------------------------------------- arms: drawn frog arms that reach for the hands
# The body sprite's SpriteAnimNodes are keyed per frame in the AnimationClips (scripts/clip_curves.py ->
# _dump/sprite_nodes.json). Node 6 is the weapon grip, where the game draws the wielded weapon: pixels from the
# sprite pivot, y down, angle in degrees in the same y-down space.
NODES_PATH = ROOT + "/_dump/sprite_nodes.json"
NODES = {}
NEAR_SHOULDER, FAR_SHOULDER = (57.0, 46.0), (46.0, 50.0)  # cut-out px (the cut-out faces left)
ARM_LEN = (42.0, 30.0)            # upper arm, forearm (cut-out px)
ARM_RADII = (10.0, 8.5, 7.0)      # shoulder, elbow, wrist
HAND_RADII = (10.5, 9.0)          # along / across the forearm (a fist)
ARM_RGB, HAND_RGB = np.array([236.0, 192.0, 76.0]), np.array([118.0, 90.0, 28.0])
TWO_HANDED = {  # the far hand holds the weapon this far (world units) along it from the grip
    "PlayerSwing": 0.10, "PlayerSwingHeavy": 0.12, "PlayerSwingExhausted": 0.10, "PlayerRunHeavyAttack": 0.12,
    "PlayerAimShotgunPump": 0.30, "PlayerRifleTurn": 0.30, "PlayerPryOpen": 0.14, "PlayerUseManhole": 0.12,
}
RUN_SWING_GROUPS = {"PlayerRun", "PlayerRunStart", "PlayerRunHurt", "PlayerRunStop", "PlayerRunTurn",
                    "PlayerStumbleRun"}
RUN_SWING = (10.0, 45.0, 75.0)    # rest angle from straight down, swing amplitude, elbow bend (degrees)
RUN_STRIDE = 0.40                 # foot offset (world units) that swings an arm fully


def load_nodes():
    if not NODES and os.path.exists(NODES_PATH):
        NODES.update(json.load(open(NODES_PATH)))
    return NODES


def weapon_node(name):
    """Node 6 of this frame, else of the nearest keyed frame of the same clip strip (within 3 frames)."""
    nodes = load_nodes()
    n6 = nodes.get(name, {}).get("n6")
    if n6 is not None:
        return n6
    m = re.search(r"(\d+)(_flipped)?$", name)
    if not m:
        return None
    idx, width = int(m.group(1)), len(m.group(1))
    for k in (1, 2, 3):
        for j in (idx - k, idx + k):
            if j >= 0:
                cand = name[:m.start(1)] + str(j).zfill(width) + (m.group(2) or "")
                n6 = nodes.get(cand, {}).get("n6")
                if n6 is not None:
                    return n6
    return None


def arm_mode(group, name):
    """'weapon' (arms reach for the grip), 'swing' (running arm swing), 'paddle' (treading water) or None
    (hands on the belly)."""
    if group in ARMLESS_GROUPS or group in OVERLAY_GROUPS:
        return None
    if group in SWIM_GROUPS:
        return "paddle"
    if weapon_node(name) is not None:
        return "weapon"
    if group in RUN_SWING_GROUPS and name in LEGS:
        return "swing"
    return None


def frog_point(src, frame):
    """Cut-out point -> original canvas (bottom-left origin), with the frog's scale, facing and body tilt."""
    w, h = frame["w"], frame["h"]
    x = frame["pad"] + (src[0] if frame["face_left"] else P_W - src[0]) * w / P_W
    y = src[1] * h / P_H
    x += math.tan(math.radians(frame["tilt"])) * (P_HIP_Y * h / P_H - y)
    return frame["left"] + x, frame["bottom"] + (h - y)


def solve_elbow(s, hand, l1, l2, fwd):
    """Two-bone IK, elbow down and a little back; overlong reaches stretch the arm up to 35%."""
    dx, dy = hand[0] - s[0], hand[1] - s[1]
    d = math.hypot(dx, dy)
    if d > l1 + l2:
        k = min(d / (l1 + l2), 1.35)
        l1, l2 = l1 * k, l2 * k
        if d > l1 + l2:
            f = (l1 + l2) * 0.999 / d
            hand, dx, dy, d = (s[0] + dx * f, s[1] + dy * f), dx * f, dy * f, (l1 + l2) * 0.999
    d = max(d, abs(l1 - l2) + 1e-3, 1e-3)
    base = math.atan2(dy, dx)
    off = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2.0 * l1 * d))))
    cands = [(s[0] + l1 * math.cos(base + sg * off), s[1] + l1 * math.sin(base + sg * off)) for sg in (1, -1)]
    return min(cands, key=lambda e: (e[1] - s[1]) + 0.3 * fwd * (e[0] - s[0])), hand


def swing_arm(s, foot, l1, l2, fwd):
    """Running arm: swings opposite to the same-side foot, elbow bent."""
    rest, amp, bend = RUN_SWING
    a = math.radians(rest - amp * max(-1.0, min(1.0, foot / RUN_STRIDE)))
    b = a + math.radians(bend)
    e = (s[0] + fwd * l1 * math.sin(a), s[1] - l1 * math.cos(a))
    return e, (e[0] + fwd * l2 * math.sin(b), e[1] - l2 * math.cos(b))


def capsule(d, p0, p1, r0, r1, fill):
    n = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1.0
    nx, ny = -(p1[1] - p0[1]) / n, (p1[0] - p0[0]) / n
    d.polygon([(p0[0] + nx * r0, p0[1] + ny * r0), (p1[0] + nx * r1, p1[1] + ny * r1),
               (p1[0] - nx * r1, p1[1] - ny * r1), (p0[0] - nx * r0, p0[1] - ny * r0)], fill=fill)
    for p, r in ((p0, r0), (p1, r1)):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)


def oval(d, c, u, ra, rb, fill):
    """Ellipse centred at c with its `ra` axis along unit vector u."""
    pts = [(c[0] + u[0] * ra * math.cos(t) - u[1] * rb * math.sin(t),
            c[1] + u[1] * ra * math.cos(t) + u[0] * rb * math.sin(t))
           for t in np.linspace(0, 2 * math.pi, 28, endpoint=False)]
    d.polygon(pts, fill=fill)


def draw_arm(s, e, hand, sc, ss=3):
    """Shaded yellow upper arm and forearm with an olive hand, lit from above; returns (image, left, bottom)."""
    r0, r1, r2 = (r * sc for r in ARM_RADII)
    ha, hb = HAND_RADII[0] * sc, HAND_RADII[1] * sc
    fl0 = math.hypot(hand[0] - e[0], hand[1] - e[1]) or 1.0
    fist = (hand[0] + (hand[0] - e[0]) / fl0 * ha * 0.5, hand[1] + (hand[1] - e[1]) / fl0 * ha * 0.5)
    m = max(r0, ha) + 4
    xs, ys = (s[0], e[0], hand[0], fist[0]), (s[1], e[1], hand[1], fist[1])
    x0, y0, x1, y1 = min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m
    size = (int(math.ceil((x1 - x0) * ss)), int(math.ceil((y1 - y0) * ss)))

    def to_img(p, lift=0.0):
        return (p[0] - x0) * ss, (y1 - p[1]) * ss - lift

    S, E, H, hc = to_img(s), to_img(e), to_img(hand), to_img(fist)
    fl = math.hypot(H[0] - E[0], H[1] - E[1]) or 1.0
    u = ((H[0] - E[0]) / fl, (H[1] - E[1]) / fl)
    shape = Image.new("L", size, 0)
    ds = ImageDraw.Draw(shape)
    capsule(ds, S, E, r0 * ss, r1 * ss, 255)
    capsule(ds, E, H, r1 * ss, r2 * ss, 255)
    oval(ds, hc, u, ha * ss, hb * ss, 255)
    col = Image.new("RGB", size, tuple(int(v) for v in ARM_RGB * 0.78))
    dc = ImageDraw.Draw(col)
    for k, tone in ((0.82, 1.0), (0.45, 1.13)):  # body colour, then a highlight, shifted towards the light
        lift = (1.0 - k) * r1 * ss * 0.9
        rgb = tuple(int(v) for v in np.clip(ARM_RGB * tone, 0, 255))
        capsule(dc, to_img(s, lift), to_img(e, lift), r0 * k * ss, r1 * k * ss, rgb)
        capsule(dc, to_img(e, lift), to_img(hand, lift), r1 * k * ss, r2 * k * ss, rgb)
    oval(dc, hc, u, ha * ss, hb * ss, tuple(int(v) for v in HAND_RGB * 0.8))
    oval(dc, (hc[0], hc[1] - hb * 0.3 * ss), u, ha * 0.7 * ss, hb * 0.55 * ss, tuple(int(v) for v in HAND_RGB * 1.15))
    col = col.filter(ImageFilter.GaussianBlur(0.3 * r1 * ss))
    img = Image.merge("RGBA", (*col.split(), shape))
    img = img.resize((max(1, size[0] // ss), max(1, size[1] // ss)), Image.LANCZOS)
    return img, x0, y0


HANG_GROUPS = {"PlayerLedgeGrabSwing", "PlayerLedgePullUp", "PlayerLedgeGrabFromJump", "PlayerLedgeUpHigh",
               "PlayerClimbRope", "PlayerLedgeWobble"}
HANG_REACH = 1.15                 # arm stretch used to hang from the grip
HANG_MIN_HEIGHT = 1.6             # world units: lower poses are crouches, not a hand reaching above the head
ROPE_GROUPS = {"PlayerClimbRope"}  # hand over hand: both frog hands go where his hands grip the rope
ROPE_DROP = 0.10                  # frog shoulders this far (x frog height) below the lower hand
ROPE_GAP = 0.05                   # frog belly this far (x frog width) behind the rope
FROG_FRONT = 7.0                  # cut-out x of the belly's front (the cut-out faces left)
SWIM_GROUPS = {"PlayerSwimLoop": "crawl", "PlayerSwimIdle": "paddle"}
SWIM_CYCLE = {"PlayerSwimLoop": 10, "PlayerSwimIdle": 4}  # frames per stroke (the clips' frame ranges)


def hang_target(alpha, sil, ppu):
    """Grip of a hanging / reaching-up pose: his topmost pixels when they are a hand (narrow, well above a
    standing head), in original-canvas pixels (bottom-left origin)."""
    if (sil["y1"] - sil["y0"]) / ppu < HANG_MIN_HEIGHT and abs(sil["lean"]) < UPRIGHT_LEAN:
        return None
    hh = alpha.shape[0]
    top = hh - sil["y1"]
    rows = alpha[top:top + max(2, int(0.05 * ppu))] > ALPHA_CUT
    xs = np.nonzero(rows.any(axis=0))[0]
    if len(xs) == 0 or (xs.max() - xs.min() + 1) / ppu > 0.14:  # a head is wider than a hand
        return None
    return float(xs.mean()), float(sil["y1"] - 0.03 * ppu)


def rope_hands(rgba, ppu):
    """(upper, lower) of his two hands on the rope in original-canvas pixels (bottom-left origin), or None."""
    hands, _ = find_hands(rgba, ppu)
    if len(hands) < 2:
        return None
    hh = rgba.shape[0]
    upper, lower = sorted(((x, hh - 1 - y) for x, y, _ in hands), key=lambda p: -p[1])
    return upper, lower


def rot_point(p, size0, size1, theta):
    """Where PIL's rotate(theta, expand=True) moves image point p (top-left origin)."""
    t = math.radians(theta)
    dx, dy = p[0] - size0[0] / 2.0, p[1] - size0[1] / 2.0
    return size1[0] / 2.0 + dx * math.cos(t) + dy * math.sin(t), size1[1] / 2.0 - dx * math.sin(t) + dy * math.cos(t)


def plan_swim_arms(stroke, name, frame):
    """Crawl: each arm circles the shoulder (forward, down, back, over); paddle: small circles in front.
    The arms are half a stroke apart; the phase is the frame's place in the swim clip."""
    size0, size1, theta = frame["rot"]
    w, h, pad = frame["w"], frame["h"], frame["pad"]

    def world(src):
        x = pad + (src[0] if frame["face_left"] else P_W - src[0]) * w / P_W
        rx, ry = rot_point((x, src[1] * h / P_H), size0, size1, theta)
        return frame["left"] + rx, frame["bottom"] + (size1[1] - ry)

    sn, sf = world(NEAR_SHOULDER), world(FAR_SHOULDER)
    d = frame["head_dir"]
    fwd = 1.0 if d[0] >= 0 else -1.0
    sc = h / P_H
    l1, l2 = ARM_LEN[0] * sc, ARM_LEN[1] * sc
    n = SWIM_CYCLE.get(group_of(name), 8)
    t = (frame_index(name) % n) / float(n)
    psi0 = math.atan2(d[1], d[0])

    def hand(phase, s):
        psi = psi0 - fwd * 2.0 * math.pi * phase
        if stroke == "crawl":
            r, c = 0.88 * (l1 + l2), s
        else:
            r, c = 0.28 * (l1 + l2), (s[0] + fwd * 0.45 * (l1 + l2), s[1] - 0.1 * (l1 + l2))
        return c[0] + r * math.cos(psi), c[1] + r * math.sin(psi)

    near = solve_elbow(sn, hand(t, sn), l1, l2, fwd)
    far = solve_elbow(sf, hand(t + 0.5, sf), l1, l2, fwd)
    return draw_arm(sf, *far, sc), draw_arm(sn, *near, sc)


def plan_arms(mode, group, name, frame):
    """(far arm layer, near arm layer) as (image, left, bottom); the far arm goes behind the body."""
    ppu, fwd = frame["ppu"], (-1.0 if frame["face_left"] else 1.0)
    sc = (frame["w"] / P_W + frame["h"] / P_H) / 2.0
    l1, l2 = ARM_LEN[0] * sc, ARM_LEN[1] * sc
    sn, sf = frog_point(NEAR_SHOULDER, frame), frog_point(FAR_SHOULDER, frame)
    if mode == "hang":
        grip = frame["hang"]
        near = solve_elbow(sn, grip, l1, l2, fwd)
        far = solve_elbow(sf, (grip[0] - fwd * 0.05 * frame["w"], grip[1] - 0.01 * frame["h"]), l1, l2, fwd)
        return draw_arm(sf, *far, sc), draw_arm(sn, *near, sc)
    if mode == "rope":  # the near hand takes the upper grip
        upper, lower = frame["rope"]
        near, far = solve_elbow(sn, upper, l1, l2, fwd), solve_elbow(sf, lower, l1, l2, fwd)
        return draw_arm(sf, *far, sc), draw_arm(sn, *near, sc)
    if mode == "paddle":  # treading water: each hand sweeps a flat circle in front of the chest, half a stroke apart
        n = SWIM_CYCLE.get(group, 4)
        t = (frame_index(name) % n) / float(n)
        reach = l1 + l2

        def paddle(s, phase):
            psi = 2.0 * math.pi * (t + phase)
            return (s[0] + fwd * reach * (0.52 + 0.26 * math.cos(psi)), s[1] - reach * (0.22 + 0.12 * math.sin(psi)))

        near = solve_elbow(sn, paddle(sn, 0.0), l1, l2, fwd)
        far = solve_elbow(sf, paddle(sf, 0.5), l1, l2, fwd)
        return draw_arm(sf, *far, sc), draw_arm(sn, *near, sc)
    if mode == "swing":
        plan = LEGS[name]
        near, far = swing_arm(sn, plan[0], l1, l2, fwd), swing_arm(sf, plan[2], l1, l2, fwd)
    else:
        n6 = weapon_node(name)
        px, py = frame["pivot"]
        grip = (px + n6["x"], py - n6["y"])
        near = solve_elbow(sn, grip, l1, l2, fwd)
        if group in TWO_HANDED and n6.get("a") is not None:
            a = math.radians(n6["a"])
            off = TWO_HANDED[group] * ppu
            far = solve_elbow(sf, (grip[0] + off * math.cos(a), grip[1] - off * math.sin(a)), l1, l2, fwd)
        else:
            far = swing_arm(sf, 0.0, l1, l2, fwd)  # resting, mostly hidden behind the body
    return draw_arm(sf, *far, sc), draw_arm(sn, *near, sc)


# ---------------------------------------------------------------- legs: follow the original character's feet
def collect_feet(env, counts, store):
    """Foot offsets (world units from the torso, forward +) of every upright body frame in `env`."""
    by_id = {o.path_id: o for o in env.objects}
    for o in env.objects:
        if o.type.name != "Sprite":
            continue
        tree = o.read_typetree()
        name = tree["m_Name"]
        group = group_of(name)
        if classify(group) != "body":
            continue
        alpha = np.asarray(by_id[tree["m_RD"]["texture"]["m_PathID"]].read().image.convert("RGBA"))[..., 3]
        sil = silhouette(alpha)
        if sil is None or not upright(sil):
            continue
        fi = foot_info(alpha, sil, face_left_of(name, group, counts))
        if fi is None:
            continue
        ppu = tree["m_PixelsToUnits"]
        store[name] = dict(two=fi["two"], **{k: fi[k] / ppu for k in ("front", "back", "lift_front", "lift_back")})


def plan_legs(store):
    """Assign the frog's near/far leg to the original's front/back foot, swapping whenever the feet pass each
    other, so a walk cycle alternates legs instead of scissoring."""
    seqs = {}
    for name, fi in store.items():
        key = group_of(name) + ("_flipped" if name.endswith("_flipped") else "")
        seqs.setdefault(key, []).append((frame_index(name), name, fi))
    swaps = filled = 0
    for key, seq in seqs.items():
        seq.sort()
        swap = crossing = False
        prev = None
        toggles = 0
        plans = []  # [name, plan or None (feet overlap: one merged blob)]
        for idx, name, fi in seq:
            if prev is not None and idx - prev > 3:
                swap = crossing = False
            prev = idx
            sep = fi["front"] - fi["back"] if fi["two"] else 0.0
            if sep < CROSS_SEP:
                plans.append([name, None])
                crossing = True
                continue
            if crossing:
                swap, crossing = not swap, False
                toggles += 1
            f, b = (fi["front"], fi["lift_front"]), (fi["back"], fi["lift_back"])
            near, far = (b, f) if swap else (f, b)
            plans.append([name, (near[0], near[1], far[0], far[1])])
        swaps += toggles
        loop = group_of(key) in LOOP_GROUPS
        filled += fill_crossings(plans, loop, loop and toggles % 2 == 1)
        for name, plan in plans:
            if plan is not None:
                LEGS[name] = plan
    print(f"leg plans: {len(LEGS)} frames in {len(seqs)} sequences, {swaps} leg swaps, {filled} passing frames")


LOOP_GROUPS = {"PlayerWalk", "PlayerRun", "PlayerCrouchWalk", "PlayerWalkHurt", "PlayerWalkHurtSevere",
               "PlayerRunHurt", "PlayerStairsWalkDown", "PlayerStairsWalkUp", "PlayerWalkWater", "PlayerMapWalk",
               "PlayerCartWalk", "PlayerCartReverse", "PlayerAimWalk"}
SWING_LIFT = 0.06  # world units: how high the passing foot is raised


def fill_crossings(plans, loop, wrap_swap=False):
    """Where the feet overlap the silhouette gives one merged blob, not two feet: carry each foot through on a
    straight line between the frames around it (wrapping round a looping clip), the planted foot sliding back
    and the swinging foot passing forward with a small lift. A loop with an odd number of leg swaps comes back
    round with near and far exchanged (wrap_swap). Returns the number of frames filled."""
    n = len(plans)
    known = [i for i, p in enumerate(plans) if p[1] is not None]
    if not known or len(known) == n:
        return 0
    count = 0
    for i, p in enumerate(plans):
        if p[1] is not None:
            continue
        before = [k for k in known if k < i]
        after = [k for k in known if k > i]
        if loop:
            a = before[-1] if before else known[-1]
            b = after[0] if after else known[0]
        else:
            a = before[-1] if before else after[0]
            b = after[0] if after else before[-1]
        pa, pb = plans[a][1], plans[b][1]
        if wrap_swap and a > b:
            pb = (pb[2], pb[3], pb[0], pb[1])
        span = (b - a) % n if loop else max(1, b - a)
        t = ((i - a) % n) / float(span) if span else 0.5
        if a == b:
            p[1] = pa
        else:
            near = pa[0] + (pb[0] - pa[0]) * t
            far = pa[2] + (pb[2] - pa[2]) * t
            lift = SWING_LIFT * math.sin(math.pi * t)
            p[1] = (near, lift if pb[0] > pa[0] else 0.0, far, lift if pb[2] > pa[2] else 0.0)
        count += 1
    return count


# ---------------------------------------------------------------- overlays
def skin_mask(rgb, lum):
    """The game's flat palette: skin (136,112,96), sleeve brown (80,64,56), shadow (24,24,24), cuff (160,168,168)."""
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    return (lum > 95) & (lum < 175) & (rgb[..., 0] > rgb[..., 2] + 25) & (sat > 0.18)


def find_hands(rgba, ppu):
    """The original character's visible hands: skin blobs that are not the face, biggest first.
    Returns ([(x, y, area_px)], face_box or None) in image pixels (top-left origin). The face is the skin blob
    touching the hair, the largest dark blob in the upper part of the head end."""
    rgb, alpha = rgba[..., :3].astype(np.float32), rgba[..., 3]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    opaque = alpha > 200
    skin = (skin_mask(rgb, lum) & opaque).astype(np.uint8)
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(skin)
    if n < 2:
        return [], None
    dark = ((lum < 45) & opaque).astype(np.uint8)
    dn, dlab, dst, _ = cv2.connectedComponentsWithStats(dark)
    near = cv2.dilate(skin, np.ones((7, 7), np.uint8))
    face, best = None, 0
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA]
        if area < 0.0004 * ppu * ppu:
            continue
        ring = (cv2.dilate((lab == i).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0) & ~(lab == i)
        # hair or glasses next to it: dark pixels that belong to a big, compact dark blob
        touching = np.unique(dlab[ring & (dark > 0)])
        score = sum(dst[j, cv2.CC_STAT_AREA] for j in touching if j > 0 and
                    dst[j, cv2.CC_STAT_AREA] < 0.08 * ppu * ppu)
        inner = dark[st[i, cv2.CC_STAT_TOP]:st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT],
                     st[i, cv2.CC_STAT_LEFT]:st[i, cv2.CC_STAT_LEFT] + st[i, cv2.CC_STAT_WIDTH]].sum()
        score += 3 * inner  # glasses / eyes / mouth inside the face
        if score > best:
            face, best = i, score
    del near
    hands = []
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA]
        if i == face or area < 0.0015 * ppu * ppu:
            continue
        hands.append((float(cen[i][0]), float(cen[i][1]), int(area)))
    hands.sort(key=lambda hnd: -hnd[2])
    box = None
    if face is not None and best > 0.0008 * ppu * ppu:
        x, y, w, h = (st[face, k] for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        box = (x, y, x + w, y + h)
    else:
        hands = []  # no face found: the skin may all be face (back views show none), do not guess
    return hands[:2], box


def remove_head(rgb, lum, alpha):
    """Drop the head (hair, face, glasses, collar) that the rifle-draw arm overlay carries; keep the sleeve."""
    opaque = alpha > 20
    ys = np.nonzero(opaque)[0]
    if len(ys) == 0:
        return alpha
    top, bot = ys.min(), ys.max()
    region = np.zeros_like(opaque)
    region[: int(top + 0.45 * (bot - top)) + 1] = True
    hair = (opaque & region & (lum < 45)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(hair)
    if n < 2:
        return alpha
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[i, cv2.CC_STAT_AREA] < 50:
        return alpha
    hx, hy, hw, hh = (st[i, k] for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
    yy, xx = np.mgrid[0:alpha.shape[0], 0:alpha.shape[1]]
    bx0, bx1, by1 = hx - 0.15 * hw, hx + 1.6 * hw, hy + 2.3 * hh
    box = (xx >= bx0) & (xx <= bx1) & (yy <= by1)
    sleeve = (lum >= 45) & (lum <= 95) & ~skin_mask(rgb, lum)
    head = opaque & box & ~sleeve
    head = cv2.morphologyEx(head.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)) > 0
    out = alpha.copy()
    out[head & box] = 0
    # what is left of the head (coat collar, ear) is separate from the arm: drop pieces centred in the head box
    n, lab, st, cen = cv2.connectedComponentsWithStats((out > 20).astype(np.uint8))
    if n > 2:
        keep = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        total = max(1, (out > 20).sum())
        for i in range(1, n):
            cx, cy = cen[i]
            in_head = bx0 <= cx <= bx1 and cy <= by1
            if i != keep and (in_head or st[i, cv2.CC_STAT_AREA] < 0.02 * total):
                out[lab == i] = 0
    return out


def render_overlay(img, group):
    a = np.asarray(img).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3]
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    if group == "PlayerRifleDrawArms":
        alpha = remove_head(rgb, lum, alpha)
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    cuff = (lum > 140) & ((mx - mn) / np.maximum(mx, 1.0) < 0.15)  # shirt cuff: no bright band on the frog
    shade = np.where(cuff, 0.95, np.clip(0.45 + lum / 160.0, 0.45, 1.15))
    sleeve = FROG_YELLOW * shade[..., None]
    hand = FROG_HAND * np.clip(lum / 117.0, 0.6, 1.25)[..., None]
    out = np.where(skin_mask(rgb, lum)[..., None], hand, sleeve)
    return Image.fromarray(np.dstack([np.clip(out, 0, 255), alpha]).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- sprite mesh
def original_winding(rd):
    data = bytes(rd["m_VertexData"]["m_DataSize"])
    i, j, k = struct.unpack_from("<3H", bytes(rd["m_IndexBuffer"]), 0)
    (ax, ay), (bx, by), (cx, cy) = [struct.unpack_from("<2f", data, n * 12) for n in (i, j, k)]
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def apply_sprite(tree, info):
    w2, h2, p2x, p2y, ppu = info["w2"], info["h2"], info["p2x"], info["p2y"], info["ppu"]
    piv = {"x": p2x / w2, "y": p2y / h2}
    tree["m_Rect"] = {"x": 0.0, "y": 0.0, "width": float(w2), "height": float(h2)}
    tree["m_Pivot"] = piv
    tree["m_Offset"] = {"x": (piv["x"] - 0.5) * w2, "y": (piv["y"] - 0.5) * h2}
    rd = tree["m_RD"]
    sign = original_winding(rd)
    rd["textureRect"] = {"x": 0.0, "y": 0.0, "width": float(w2), "height": float(h2)}
    rd["textureRectOffset"] = {"x": 0.0, "y": 0.0}
    rd["settingsRaw"] = rd["settingsRaw"] & ~64  # meshType Tight -> FullRect
    rd["uvTransform"] = {"x": float(ppu), "y": float(p2x), "z": float(ppu), "w": float(p2y)}
    l, r, b, t = -p2x / ppu, (w2 - p2x) / ppu, -p2y / ppu, (h2 - p2y) / ppu
    pos = [(l, b), (r, b), (l, t), (r, t)]
    tris = [(0, 2, 1), (2, 3, 1)]

    def area(i, j, k):
        (ax, ay), (bx, by), (cx, cy) = pos[i], pos[j], pos[k]
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    if (area(*tris[0]) > 0) != (sign > 0):
        tris = [(i, k, j) for i, j, k in tris]
    data = b"".join(struct.pack("<3f", x, y, 0.0) for x, y in pos)
    data += b"".join(struct.pack("<2f", u, v) for u, v in [(0, 0), (1, 0), (0, 1), (1, 1)])
    vd = rd["m_VertexData"]
    vd["m_VertexCount"] = 4
    vd["m_DataSize"] = data
    rd["m_IndexBuffer"] = list(struct.pack("<6H", *[i for tri in tris for i in tri]))
    sm = rd["m_SubMeshes"][0]
    sm.update({"firstByte": 0, "indexCount": 6, "topology": 0, "baseVertex": 0, "firstVertex": 0, "vertexCount": 4})
    rd["m_SubMeshes"] = [sm]


# ---------------------------------------------------------------- bundles
def patch_index():
    """{bundle file: [sprite names]} for patch bundles."""
    idx = {}
    for line in open(PATCH_INDEX, encoding="utf-8"):
        fn = line.split(" ", 1)[0]
        idx[fn] = re.findall(r"'([^'(]+)\(", line)
    return idx


def group_counts(main_names, pidx):
    counts = {}
    for n in list(main_names) + [n for ns in pidx.values() for n in ns]:
        g = group_of(n)
        counts[g] = counts.get(g, 0) + 1
    return counts


def process_env(env, counts, stats, only=None, previews=None):
    by_id = {o.path_id: o for o in env.objects}
    changed = False
    for o in [o for o in env.objects if o.type.name == "Sprite"]:
        tree = o.read_typetree()
        name = tree["m_Name"]
        if only is not None and name not in only:
            continue
        group = group_of(name)
        kind = classify(group)
        if kind == "skip":
            stats["kept"] += 1
            continue
        tex = by_id[tree["m_RD"]["texture"]["m_PathID"]].read()
        img = tex.image.convert("RGBA")
        info = None
        if kind == "hide":
            new = Image.new("RGBA", img.size, (0, 0, 0, 0))
        elif kind == "overlay":
            new = render_overlay(img, group)
        else:
            res = render_body(tree, img, group, name, counts)
            if res is None:
                stats["empty"] += 1
                continue
            new, info = res
            stats["grown"] += new.size != img.size
        stats[kind] += 1
        if previews is not None:
            pivot = (tree["m_Pivot"]["x"] * img.width, tree["m_Pivot"]["y"] * img.height)
            previews.append((name, img, new, info, pivot))
            continue
        fmt = TextureFormat.RGBA32 if tex.m_TextureFormat == TextureFormat.RGBA32 else TextureFormat.DXT5
        if fmt == TextureFormat.DXT5 and (new.width % 4 or new.height % 4):
            fmt = TextureFormat.RGBA32
        tex.set_image(new, target_format=fmt, mipmap_count=1)
        tex.save()
        if info is not None:
            apply_sprite(tree, info)
            o.save_typetree(tree)
        changed = True
    return changed


def measure_rest(env):
    """Average idle foot offsets of the original character (forward, world units)."""
    fronts, backs = [], []
    by_id = {o.path_id: o for o in env.objects}
    for o in env.objects:
        if o.type.name != "Sprite":
            continue
        t = o.read_typetree()
        if group_of(t["m_Name"]) not in ("PlayerIdle", "PlayerIdle_v", "PlayerIdle_v2_loop"):
            continue
        img = by_id[t["m_RD"]["texture"]["m_PathID"]].read().image.convert("RGBA")
        alpha = np.asarray(img)[..., 3]
        sil = silhouette(alpha)
        fi = foot_info(alpha, sil, False) if sil else None
        if fi and fi["two"]:
            fronts.append(fi["front"] / t["m_PixelsToUnits"])
            backs.append(fi["back"] / t["m_PixelsToUnits"])
    if fronts:
        REST[0], REST[1] = float(np.mean(fronts)), float(np.mean(backs))
    print(f"idle foot offsets: front={REST[0]:.3f} back={REST[1]:.3f} (n={len(fronts)})")


def new_stats():
    return {"body": 0, "overlay": 0, "hide": 0, "empty": 0, "grown": 0, "kept": 0}


def sheet(previews, path, cell_h=420, cols=5):
    from PIL import ImageDraw as _D
    tiles = []
    for name, old, new, info, _ in previews:
        pair = Image.new("RGBA", (old.width + new.width + 30, max(old.height, new.height) + 20), (70, 70, 70, 255))
        for k, im in enumerate((old, new)):
            bg = Image.new("RGBA", im.size, (110, 110, 110, 255))
            bg.alpha_composite(im)
            pair.paste(bg, (10 + k * (old.width + 10), pair.height - 10 - im.height))
        d = _D.Draw(pair)
        d.text((12, 4), name, fill=(255, 255, 0, 255))
        if info is not None:
            x, y = 20 + old.width + info["p2x"], pair.height - 10 - info["p2y"]
            d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(255, 0, 0, 255), width=3)
        pair.thumbnail((cell_h * 2, cell_h))
        tiles.append(pair)
    cw = max(t.width for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new("RGBA", (cw * cols, cell_h * rows), (40, 40, 40, 255))
    for i, t in enumerate(tiles):
        out.paste(t, ((i % cols) * cw, (i // cols) * cell_h + cell_h - t.height))
    out.thumbnail((2400, 2400))
    out.save(path)
    print("preview", path, out.size)


def strip(previews, path, scale=0.35):
    """Frog frames over a faint copy of the original, all pivots on one baseline (to check the feet)."""
    cells = []
    for name, old, new, info, _ in previews:
        if info is None:
            continue
        cell = Image.new("RGBA", new.size, (0, 0, 0, 0))
        ghost = np.asarray(old).copy()
        ghost[..., 3] = (ghost[..., 3] * 0.45).astype(np.uint8)
        ghost[..., :3] = 255 - ghost[..., :3] // 3
        cell.alpha_composite(Image.fromarray(ghost, "RGBA"),
                             (int(info["ox"]), new.height - int(info["oy"]) - old.height))
        cell.alpha_composite(new)
        cells.append((name, cell, info["p2x"], new.height - info["p2y"]))
    if not cells:
        return
    above = max(c[3] for c in cells)
    below = max(c[1].height - c[3] for c in cells)
    step = max(c[1].width for c in cells) * 0.62
    out = Image.new("RGBA", (int(step * len(cells) + max(c[1].width for c in cells)), int(above + below + 40)),
                    (60, 60, 60, 255))
    d = ImageDraw.Draw(out)
    base = above + 30
    d.line([(0, base), (out.width, base)], fill=(200, 60, 60, 255), width=3)
    for i, (name, cell, px, py) in enumerate(cells):
        x = int(i * step + step / 2 + 40 - px)
        out.alpha_composite(cell, (max(0, x), int(base - py)))
        d.text((max(0, x) + int(px) - 30, 4 + (i % 2) * 14), name[-14:], fill=(255, 255, 0, 255))
    out = out.resize((max(1, int(out.width * scale)), max(1, int(out.height * scale))), Image.LANCZOS)
    out.save(path)
    print("strip", path, out.size)


def pairs(previews, groups, path, scale=0.4):
    """Each token 'body+overlay' (sprite names): original layers vs frog layers, stacked on their pivots."""
    by = {p[0]: p for p in previews}
    tiles = []
    for token in groups:
        names = [n for n in token.split("+") if n in by]
        if not names:
            continue
        for use_new in (False, True):
            layers = []
            for n in names:
                _, old, new, info, pivot = by[n]
                im = new if use_new else old
                pv = (info["p2x"], info["p2y"]) if use_new and info is not None else pivot
                layers.append((im, pv[0], im.height - pv[1]))
            left = max(px for _, px, _ in layers)
            top = max(py for _, _, py in layers)
            wd = max(im.width - px for im, px, _ in layers) + left
            ht = max(im.height - py for im, _, py in layers) + top
            tile = Image.new("RGBA", (int(wd) + 20, int(ht) + 40), (90, 90, 90, 255))
            for im, px, py in layers:
                tile.alpha_composite(im, (int(10 + left - px), int(30 + top - py)))
            ImageDraw.Draw(tile).text((8, 6), ("frog " if use_new else "orig ") + token, fill=(255, 255, 0, 255))
            tiles.append(tile)
    hmax = max(t.height for t in tiles)
    out = Image.new("RGBA", (sum(t.width for t in tiles) + 10 * len(tiles), hmax), (40, 40, 40, 255))
    x = 0
    for t in tiles:
        out.paste(t, (x, hmax - t.height))
        x += t.width + 10
    out = out.resize((max(1, int(out.width * scale)), max(1, int(out.height * scale))), Image.LANCZOS)
    out.save(path)
    print("pairs", path, out.size)


def source_bundle(fn):
    """Original copy of a patch bundle: the backup once the mod is installed, else the game folder."""
    backup = os.path.join(BACKUP_PATCHES, fn)
    return backup if os.path.exists(backup) else os.path.join(AA, fn)


def player_patch_bundles(pidx):
    fns = [fn for fn, names in sorted(pidx.items())
           if any(classify(group_of(n)) in ("body", "overlay", "hide") for n in names)]
    return fns + EXTRA_BUNDLES


def main():
    mode = sys.argv[1]
    pidx = patch_index()
    main_env = UnityPy.load(ORIG_MAIN)
    main_names = [o.read().m_Name for o in main_env.objects if o.type.name == "Sprite"]
    counts = group_counts(main_names, pidx)
    measure_rest(main_env)
    patch_fns = player_patch_bundles(pidx)
    feet = {}
    collect_feet(main_env, counts, feet)
    for fn in patch_fns:
        collect_feet(UnityPy.load(source_bundle(fn)), counts, feet)
    plan_legs(feet)
    stats = new_stats()
    if mode == "main":
        process_env(main_env, counts, stats)
        with open(sys.argv[2], "wb") as f:
            f.write(main_env.file.save(packer="lz4"))
        print(stats, "saved", sys.argv[2])
    elif mode == "patches":
        out_dir = sys.argv[2]
        os.makedirs(out_dir, exist_ok=True)
        written = []
        for fn in patch_fns:
            env = UnityPy.load(source_bundle(fn))
            if process_env(env, counts, stats):
                with open(os.path.join(out_dir, fn), "wb") as f:
                    f.write(env.file.save(packer="lz4"))
                written.append(fn)
        with open(os.path.join(out_dir, "bundles.txt"), "w", encoding="utf-8") as f:
            f.write("".join(fn + "\n" for fn in written))
        print(stats, f"wrote {len(written)} bundles to {out_dir}")
    elif mode in ("preview", "strip", "pairs"):
        tokens = sys.argv[3:]
        want = [n for t in tokens for n in t.split("+")]
        previews = []
        process_env(main_env, counts, stats, only=set(want), previews=previews)
        for fn in patch_fns:
            names = set(pidx.get(fn, [])) if fn in pidx else None
            if names is None or set(want) & names:
                process_env(UnityPy.load(source_bundle(fn)), counts, stats, only=set(want), previews=previews)
        order = {n: i for i, n in enumerate(want)}
        previews.sort(key=lambda p: order.get(p[0], 0))
        print(stats)
        if mode == "strip":
            strip(previews, sys.argv[2], float(os.environ.get("SCALE", 0.35)))
        elif mode == "pairs":
            pairs(previews, tokens, sys.argv[2], float(os.environ.get("SCALE", 0.4)))
        else:
            sheet(previews, sys.argv[2], int(os.environ.get("CELL_H", 420)), int(os.environ.get("COLS", 5)))


if __name__ == "__main__":
    main()
