"""Extras on top of the frog body: an idle laugh cut from a video (with its sound), the thinking frog as the
protagonist's dialogue portrait, and Unity's own audio switched on so the laugh can be heard.

- The laugh lives in the player's clip bundle, next to the Idle_Variants PlayMaker template: one Texture2D and
  Sprite per frame (frogmod/laugh, made by laugh_frames.py), a new AnimationClip (a copy of the LookAround
  flourish with its sprite curve rewritten) and a new AudioClip (PCM16 in an FSB5 bank, kept in a .resource
  node of the bundle as Unity does). The template then waits until LAUGH_AFTER seconds of standing still and
  plays the laugh in LAUGH_STATE together with AddComponent(AudioSource) + AudioPlay(one shot). The
  AudioSource is removed when the state exits, so walking off cuts the sound.
- The game plays all its sound through FMOD and ships with Unity audio disabled
  (globalgamemanagers: AudioManager.m_DisableAudio), so that one flag is cleared.
- portrait_Player* (the face shown next to the protagonist's lines, e.g. on the phone) become the thinking frog.

usage: python -P -E frog_extras.py <build_dir>
  writes <build_dir>/patches/<clip bundle>, <build_dir>/patches/<portrait bundle> (added to bundles.txt) and
  <build_dir>/globalgamemanagers. Run it after `frogify.py patches`, which rewrites bundles.txt.
"""
import copy
import hashlib
import io
import json
import os
import struct
import sys
import wave

import numpy as np
import UnityPy
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from UnityPy.enums import ClassIDType, TextureFormat
from UnityPy.files.ObjectReader import ObjectReader
from UnityPy.files.SerializedFile import SerializedType
from UnityPy.helpers import TypeTreeHelper
from UnityPy.helpers.Tpk import get_typetree_node
from UnityPy.helpers.TypeTreeNode import TypeTreeNode
from UnityPy.streams import EndianBinaryReader, EndianBinaryWriter

sys.path.insert(0, os.path.dirname(__file__))
from frogify import GAME, ORIG_MAIN, ROOT, apply_sprite, source_bundle  # noqa: E402
from laugh_frames import border_connected, largest  # noqa: E402

CLIPS = "team17_auto_base_characters_assets_player.bundle"
PORTRAITS = "sprites-characterportraits_assets_all.bundle"
STATUS = "team17_auto_base_general_compressed_assets_health.bundle"   # backpack (status page) UI art
STATUS_PHOTO = "fine"    # the protagonist's photo in the backpack's polaroid (InGameMenu/.../PhotoMask/Portrait)
GGM = "Carpenter_Data/globalgamemanagers"
BACKUP_GGM = ROOT + "/frogmod/backup/globalgamemanagers"
TEMPLATE = 5633624329725344446       # Idle_Variants.asset: the standing-idle PlayMaker template
LOOK_AROUND = -1197102233214644118   # Player_StandingIdleLookAround: the laugh clip is a copy of it
IDLE_LOOP = 5318746824419018908      # Player_StandingIdleLoop: its flashlight node (n5) is held during the laugh
SPRITE_TEMPLATE = "PlayerIdle00"     # sprite + texture in the main bundle the new frames are copied from
LAUGH_DIR = ROOT + "/frogmod/laugh"
LAUGH_STATE = "IdleFlourish_1"
LAUGH_AFTER = 10.0       # seconds of standing still before the laugh starts
LAUGH_VOLUME = 0.8
LAUGH_PPU = 230.0        # texture px per world unit: the frog is about 400 px tall
LAUGH_HEIGHT = 1.74      # world units, feet to head in the first frame: the idle frog's height
LAUGH_FEET = 0.068       # the idle frog's feet stand this far above the sprite pivot
PORTRAIT_SRC = ROOT + "/frogmod/source/frog_thinking.png"
PLAYMAKER = "HutongGames.PlayMaker."
FLT_MAX_NEG, F_INF = 0xFF7FFFFF, 0x7F800000


def stable_id(name):
    """Deterministic 64-bit path id for a new object, so rebuilds give identical bundles."""
    return int.from_bytes(hashlib.md5(("silver-pines-frog/" + name).encode()).digest()[:8], "little", signed=True)


# ---------------------------------------------------------------- new objects in a serialized file
def add_object(sf, type_index, path_id, tree):
    """Serialize tree with the file's type tree for type_index and add it as a new object."""
    st = sf.types[type_index]
    w = EndianBinaryWriter(endian=sf.header.endian)
    TypeTreeHelper.write_typetree(tree, st.node, w, sf)
    data = w.bytes
    if path_id in sf.objects:
        raise ValueError(f"path id {path_id} already used")
    obj = ObjectReader(sf, EndianBinaryReader(data, endian=sf.header.endian), path_id, type_index, st,
                       st.class_id, ClassIDType(st.class_id), 0, len(data), None, None, data=data)
    sf.objects[path_id] = obj
    sf.mark_changed()
    return obj


def type_index(sf, st):
    """Index of the engine type st in sf.types, adding a copy (type tree and hash) when the file lacks it."""
    for i, t in enumerate(sf.types):
        if t.class_id == st.class_id and t.script_type_index == -1:
            return i
    sf.types.append(copy.copy(st))
    return len(sf.types) - 1


def tpk_type(sf, class_id):
    """A type for a class no file of the game uses (AudioClip), from UnityPy's type tree package. Its hash is
    left blank, so Unity reads the objects through the stored type tree."""
    def blob_node(n):  # the package leaves the flags a type tree blob needs unset
        return TypeTreeNode(m_Level=n.m_Level, m_Type=n.m_Type, m_Name=n.m_Name, m_ByteSize=n.m_ByteSize,
                            m_Version=n.m_Version, m_Children=[blob_node(c) for c in n.m_Children],
                            m_TypeFlags=1 if n.m_Type == "Array" else 0, m_VariableCount=n.m_VariableCount,
                            m_Index=n.m_Index, m_MetaFlag=n.m_MetaFlag, m_RefTypeHash=0)

    node = blob_node(get_typetree_node(class_id, sf.version))
    st = object.__new__(SerializedType)
    st.class_id, st.is_stripped_type, st.script_type_index = class_id, False, -1
    st.script_id, st.old_type_hash, st.node = None, bytes(16), node
    st.m_ClassName = st.m_NameSpace = st.m_AssemblyName = None
    st.type_dependencies, st.type_tree_content_hash, st.type_tree_serialized_size = (), None, None
    sf.types.append(st)
    return len(sf.types) - 1


# ---------------------------------------------------------------- laugh frames
def laugh_tiles():
    """[(name, RGBA image, apply_sprite info)]: frames scaled to LAUGH_PPU, trimmed, padded to 4 px blocks,
    all placed so the first frame's feet stand where the idle frog's do."""
    meta = json.load(open(LAUGH_DIR + "/laugh.json"))
    frames = [Image.open(f"{LAUGH_DIR}/{n}.png").convert("RGBA") for n in meta["frames"]]
    a0 = np.asarray(frames[0])[..., 3] > 40
    ys, xs = np.nonzero(a0)
    scale = LAUGH_PPU / ((ys.max() + 1 - ys.min()) / LAUGH_HEIGHT)
    w0, h0 = frames[0].size
    cw, ch = round(w0 * scale), round(h0 * scale)
    anchor_x = (xs.min() + xs.max() + 1) / 2 * cw / w0     # canvas x of world x = 0 (frame 0 centred)
    feet_y = (ys.max() + 1) * ch / h0                      # canvas row of the first frame's soles
    # the frog drifts sideways while laughing; while it gets up at the end it slides back to where it started,
    # so the idle pose that follows does not jump
    _, xs_end = np.nonzero(np.asarray(frames[-1])[..., 3] > 40)
    drift = ((xs_end.min() + xs_end.max() + 1) / 2 - (xs.min() + xs.max() + 1) / 2) * cw / w0
    n_up = round((meta["get_up"][1] - meta["get_up"][0]) * meta["fps"])
    out = []
    for i, (name, im) in enumerate(zip(meta["frames"], frames)):
        back = drift * min(1.0, max(0.0, (i - (len(frames) - n_up) + 1) / n_up))
        canvas = np.asarray(im.convert("RGBa").resize((cw, ch), Image.LANCZOS).convert("RGBA")).copy()
        canvas[canvas[..., 3] < 3] = 0
        ys, xs = np.nonzero(canvas[..., 3])
        x0, y0 = max(0, xs.min() - 1), max(0, ys.min() - 1)
        w = -(-(xs.max() + 2 - x0) // 4) * 4
        h = -(-(ys.max() + 2 - y0) // 4) * 4
        tile = np.zeros((h, w, 4), np.uint8)
        part = canvas[y0:y0 + h, x0:x0 + w]
        tile[:part.shape[0], :part.shape[1]] = part
        info = {"w2": w, "h2": h, "p2x": anchor_x + back - x0, "p2y": (y0 + h - feet_y) - LAUGH_FEET * LAUGH_PPU,
                "ppu": LAUGH_PPU}
        out.append((name, Image.fromarray(tile, "RGBA"), info))
    return out, meta["fps"]


def sprite_template():
    """(sprite tree, texture raw data, sprite type, texture type) of SPRITE_TEMPLATE in the original bundle."""
    env = UnityPy.load(ORIG_MAIN)
    by = {o.path_id: o for o in env.objects}
    for o in env.objects:
        if o.type == ClassIDType.Sprite and o.peek_name() == SPRITE_TEMPLATE:
            tree = o.read_typetree()
            tex = by[tree["m_RD"]["texture"]["m_PathID"]]
            return tree, tex.get_raw_data(), o.serialized_type, tex.serialized_type
    raise KeyError(SPRITE_TEMPLATE)


def add_laugh_sprites(sf, tiles):
    """New Texture2D (DXT5) + Sprite objects; returns the sprites' path ids in frame order."""
    s_tree, t_raw, s_type, t_type = sprite_template()
    si, ti = type_index(sf, s_type), type_index(sf, t_type)
    ids = []
    for name, img, info in tiles:
        tex_id, spr_id = stable_id(name + ".tex"), stable_id(name)
        tobj = ObjectReader(sf, EndianBinaryReader(t_raw, endian=sf.header.endian), tex_id, ti, sf.types[ti],
                            28, ClassIDType.Texture2D, 0, len(t_raw), None, None, data=t_raw)
        sf.objects[tex_id] = tobj
        tex = tobj.read()
        tex.m_Name = name
        tex.set_image(img, target_format=TextureFormat.DXT5, mipmap_count=1)
        tex.save()
        tree = copy.deepcopy(s_tree)
        tree["m_Name"] = name
        tree["m_PixelsToUnits"] = float(info["ppu"])
        tree["m_PhysicsShape"] = []
        guid = hashlib.md5(name.encode()).digest()
        tree["m_RenderDataKey"] = ({f"data[{k}]": struct.unpack_from("<I", guid, 4 * k)[0] for k in range(4)},
                                   21300000)
        tree["m_RD"]["texture"] = {"m_FileID": 0, "m_PathID": tex_id}
        apply_sprite(tree, info)
        add_object(sf, si, spr_id, tree)
        ids.append(spr_id)
    return ids


# ---------------------------------------------------------------- laugh clip
def streamed(frames):
    """m_StreamedClip words from [(time, [(curve, value)])]: constant (stepped) keys between the -FLT_MAX and
    +inf sentinel frames Unity writes."""
    out = bytearray()
    for t, keys in frames:
        out += struct.pack("<I", t) if isinstance(t, int) and t in (FLT_MAX_NEG, F_INF) else struct.pack("<f", t)
        out += struct.pack("<i", len(keys))
        for curve, value in keys:
            out += struct.pack("<i4f", curve, 0.0, 0.0, 0.0, value)
    return list(struct.unpack(f"<{len(out) // 4}I", out))


def laugh_clip(template, idle, sprite_ids, fps):
    """Copy of the LookAround clip (bindings: flashlight node n5 x/y/angle, then the sprite) showing sprite_ids
    at fps, with n5 held at the idle loop's first values."""
    from clip_curves import decode
    n5 = [decode(idle)[0][c][0][1][3] for c in range(3)]
    n = len(sprite_ids)
    stop = n / fps
    frames = [(FLT_MAX_NEG, [(0, n5[0]), (1, n5[1]), (2, n5[2]), (3, 0.0)]),
              (0.0, [(0, n5[0]), (1, n5[1]), (2, n5[2])])]
    frames += [(i / fps, [(3, float(i))]) for i in range(1, n)]
    frames.append((F_INF, []))
    words = streamed(frames)
    clip = copy.deepcopy(template)
    clip["m_Name"] = "Player_FrogLaugh"
    clip["m_SampleRate"] = float(fps)
    clip["m_Events"] = []   # LookAround turns the flashlight away and back; an interrupted laugh could leave it so
    mc = clip["m_MuscleClip"]
    mc["m_StartTime"], mc["m_StopTime"] = 0.0, stop
    data = mc["m_Clip"]["data"]
    data["m_StreamedClip"] = {"data": words, "curveCount": 3, "discreteCurveCount": 1}
    data["m_DenseClip"].update({"m_FrameCount": round(stop * fps) + 2, "m_CurveCount": 0, "m_SampleRate": float(fps),
                                "m_BeginTime": 0.0, "m_SampleArray": []})
    data["m_ConstantClip"] = {"data": []}
    mc["m_ValueArrayDelta"] = [{"m_Start": v, "m_Stop": v} for v in n5] + [{"m_Start": 0.0, "m_Stop": float(n - 1)}]
    bc = clip["m_ClipBindingConstant"]
    if [b["isPPtrCurve"] for b in bc["genericBindings"]] != [0, 0, 0, 1]:
        raise ValueError("unexpected LookAround bindings")
    bc["pptrCurveMapping"] = [{"m_FileID": 0, "m_PathID": pid} for pid in sprite_ids]
    # size of the runtime clip blob Unity allocates on load; fits all 192 player clips exactly
    clip["m_MuscleClipSize"] = 2528 + 4 * len(words) + 8 * len(mc["m_ValueArrayDelta"])
    return clip


# ---------------------------------------------------------------- laugh sound
def fsb5_pcm16(pcm, channels, rate, name):
    """One-sample FSB5 bank (the container Unity keeps AudioClip data in) holding interleaved PCM16."""
    rates = {8000: 1, 11000: 2, 11025: 3, 16000: 4, 22050: 5, 24000: 6, 32000: 7, 44100: 8, 48000: 9}
    samples = len(pcm) // (2 * channels)
    mode = rates[rate] << 1 | (channels - 1) << 5 | samples << 34      # no extra chunks, data at offset 0
    names = struct.pack("<I", 4) + name.encode() + b"\0"
    names += b"\0" * (-(0x3C + 8 + len(names)) % 32)                  # sample data starts 32-byte aligned
    data = pcm + b"\0" * (-len(pcm) % 32)
    head = b"FSB5" + struct.pack("<6I", 1, 1, 8, len(names), len(data), 2)   # version 1, PCM16
    head += bytes(8) + hashlib.md5(pcm).digest() + bytes(8)
    return head + struct.pack("<Q", mode) + names + data, samples


def laugh_sound():
    with wave.open(LAUGH_DIR + "/laugh.wav") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError("laugh.wav must be 16-bit PCM")
        return wf.readframes(wf.getnframes()), wf.getnchannels(), wf.getframerate()


def check_fsb(fsb, pcm, channels, rate):
    """Decode the bank with the FMOD library (as Unity will) and compare with the source samples."""
    import fmod_toolkit
    wav = next(iter(fmod_toolkit.raw_to_wav(fsb, "check", channels, rate).values()))
    with wave.open(io.BytesIO(wav)) as wf:
        got = wf.readframes(wf.getnframes())
        ok = wf.getnchannels() == channels and wf.getframerate() == rate and got[:len(pcm)] == pcm
    print(f"FMOD decodes the laugh bank: {'OK' if ok else 'MISMATCH'} ({len(got)} bytes)")
    if not ok:
        raise ValueError("FSB5 bank does not round-trip through FMOD")


# ---------------------------------------------------------------- PlayMaker template
PARAM_LISTS = {"owner": (20, "fsmOwnerDefaultParams"), "string": (18, "fsmStringParams"),
               "object": (24, "fsmObjectParams"), "bool": (17, "fsmBoolParams"),
               "float": (15, "fsmFloatParams"), "event": (23, "stringParams")}


def action_hash(field_types):
    """PlayMaker's ActionData.GetActionTypeHashCode: one-at-a-time hash of 'FieldType|...' (UTF-16LE)."""
    h = 0
    for b in "".join(t + "|" for t in field_types).encode("utf-16-le"):
        h = (h + b) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    h = (h + (h << 15)) & 0xFFFFFFFF
    return h % 100000000


def fsm_value(value, **extra):
    out = {"useVariable": 0, "name": "", "tooltip": "", "showInInspector": 0, "networkSync": 0}
    out.update(extra)
    out["value"] = value
    return out


def add_action(ad, type_name, params):
    """Append an action: params = [(field, kind, serialized value)] in the action class's field order."""
    types = {"owner": "FsmOwnerDefault", "string": "FsmString", "object": "FsmObject", "bool": "FsmBool",
             "float": "FsmFloat", "event": "FsmEvent"}
    ad["actionNames"].append(type_name)
    ad["customNames"].append("")
    ad["actionEnabled"].append(1)
    ad["actionIsOpen"].append(1)
    ad["actionStartIndex"].append(len(ad["paramName"]))
    ad["actionHashCodes"].append(action_hash([PLAYMAKER + types[k] for _, k, _ in params]))
    for field, kind, value in params:
        code, key = PARAM_LISTS[kind]
        ad["paramName"].append(field)
        ad["paramDataType"].append(code)
        ad["paramDataPos"].append(len(ad[key]))
        ad["paramByteDataSize"].append(0)
        ad[key].append(value)


def action_params(ad, index):
    """{field: (data type, position)} of action index."""
    start = ad["actionStartIndex"][index]
    end = ad["actionStartIndex"][index + 1] if index + 1 < len(ad["actionStartIndex"]) else len(ad["paramName"])
    return {ad["paramName"][i]: (ad["paramDataType"][i], ad["paramDataPos"][i]) for i in range(start, end)}


def edit_template(tree, clip_id, audio_id, wait):
    states = {s["name"]: s for s in tree["fsm"]["states"]}
    loop = states["NormalLoop"]
    ad = loop["actionData"]
    rw = ad["actionNames"].index(PLAYMAKER + "Actions.RandomWait")
    for field in ("min", "max"):
        ad["fsmFloatParams"][action_params(ad, rw)[field][1]]["value"] = wait
    for tr in loop["transitions"]:
        if tr["fsmEvent"]["name"] == "Trigger":
            tr["toState"] = LAUGH_STATE      # skip the random choice between the five flourishes
    ad = states[LAUGH_STATE]["actionData"]
    play = ad["actionNames"].index("Actions.PlaySpriteAnimation")
    ad["unityObjectParams"][action_params(ad, play)["m_animationClip"][1]] = {"m_FileID": 0, "m_PathID": clip_id}
    owner = {"ownerOption": 0, "gameObject": fsm_value({"m_FileID": 0, "m_PathID": 0})}
    add_action(ad, PLAYMAKER + "Actions.AddComponent", [
        ("gameObject", "owner", owner),
        ("component", "string", fsm_value("UnityEngine.AudioSource")),
        ("storeComponent", "object", fsm_value({"m_FileID": 0, "m_PathID": 0}, useVariable=1,
                                               typeName="UnityEngine.Component")),
        ("removeOnExit", "bool", fsm_value(1))])
    add_action(ad, PLAYMAKER + "Actions.AudioPlay", [
        ("gameObject", "owner", copy.deepcopy(owner)),
        ("volume", "float", fsm_value(LAUGH_VOLUME)),
        ("oneShotClip", "object", fsm_value({"m_FileID": 0, "m_PathID": audio_id}, typeName="UnityEngine.AudioClip")),
        ("WaitForEndOfClip", "bool", fsm_value(0)),
        ("finishedEvent", "event", "")])


def check_hashes(tree):
    """The hash formula must reproduce the template's own actions before new ones are trusted to it."""
    known = {"RandomWait": (["FsmFloat", "FsmFloat", "FsmEvent"], "System.Boolean"),
             "RandomEvent": (["FsmFloat", "FsmBool"], None)}
    seen = {}
    for s in tree["fsm"]["states"]:
        for n, h in zip(s["actionData"]["actionNames"], s["actionData"]["actionHashCodes"]):
            seen[n.rsplit(".", 1)[-1]] = h
    for name, (fsm_types, extra) in known.items():
        types = [PLAYMAKER + t for t in fsm_types] + ([extra] if extra else [])
        if action_hash(types) != seen[name]:
            raise ValueError(f"action hash formula does not match {name}")


# ---------------------------------------------------------------- clip bundle
def preload(ab, asset_id, new_ids):
    """Add new_ids to the preload range of the container asset asset_id, shifting the ranges after it."""
    table = ab["m_PreloadTable"]
    entry = next(info for _, info in ab["m_Container"] if info["asset"]["m_PathID"] == asset_id)
    end = entry["preloadIndex"] + entry["preloadSize"]
    table[end:end] = [{"m_FileID": 0, "m_PathID": pid} for pid in new_ids]
    for _, info in ab["m_Container"]:
        if info is not entry and info["preloadIndex"] >= end and info["preloadSize"]:
            info["preloadIndex"] += len(new_ids)
    entry["preloadSize"] += len(new_ids)


def build_clips(out_path):
    env = UnityPy.load(source_bundle(CLIPS))
    cab_name = next(n for n, f in env.file.files.items() if not n.endswith((".resS", ".resource")))
    sf = env.file.files[cab_name]
    by = {o.path_id: o for o in env.objects}
    tpl_obj = by[TEMPLATE]
    tpl = tpl_obj.read_typetree()
    check_hashes(tpl)

    tiles, fps = laugh_tiles()
    sprite_ids = add_laugh_sprites(sf, tiles)
    look, idle = by[LOOK_AROUND].read_typetree(), by[IDLE_LOOP].read_typetree()
    clip = laugh_clip(look, idle, sprite_ids, fps)
    clip_id = stable_id("Player_FrogLaugh")
    add_object(sf, by[LOOK_AROUND].type_id, clip_id, clip)

    pcm, channels, rate = laugh_sound()
    fsb, samples = fsb5_pcm16(pcm, channels, rate, "FrogLaugh")
    check_fsb(fsb, pcm, channels, rate)
    res = env.file.get_writeable_cab(cab_name + ".resource")
    res.write(fsb)
    res.flags = 0
    audio_id = stable_id("FrogLaugh.audio")
    add_object(sf, tpk_type(sf, 83), audio_id, {
        "m_Name": "FrogLaugh", "m_LoadType": 0, "m_Channels": channels, "m_Frequency": rate,
        "m_BitsPerSample": 16, "m_Length": samples / rate, "m_IsTrackerFormat": False, "m_Ambisonic": False,
        "m_SubsoundIndex": 0, "m_PreloadAudioData": True, "m_LoadInBackground": False, "m_Legacy3D": True,
        "m_Resource": {"m_Source": f"archive:/{cab_name}/{cab_name}.resource", "m_Offset": 0, "m_Size": len(fsb)},
        "m_CompressionFormat": 0})

    intro = by[next(s for s in tpl["fsm"]["states"] if s["name"] == "Normal")["actionData"]
               ["unityObjectParams"][0]["m_PathID"]].read_typetree()["m_MuscleClip"]["m_StopTime"]
    edit_template(tpl, clip_id, audio_id, round(LAUGH_AFTER - intro, 2))
    tpl_obj.save_typetree(tpl)

    ab_obj = next(o for o in env.objects if o.type == ClassIDType.AssetBundle)
    ab = ab_obj.read_typetree()
    tex_ids = [stable_id(name + ".tex") for name, _, _ in tiles]
    preload(ab, TEMPLATE, [clip_id, audio_id] + sprite_ids + tex_ids)
    ab_obj.save_typetree(ab)
    with open(out_path, "wb") as f:
        f.write(env.file.save(packer="lz4"))
    print(f"laugh: {len(tiles)} frames at {fps} fps ({len(tiles) / fps:.2f}s), sound {samples / rate:.2f}s, "
          f"starts after {LAUGH_AFTER:.0f}s idle (wait {LAUGH_AFTER - intro:.2f}s + intro {intro:.2f}s) -> {out_path}")


# ---------------------------------------------------------------- portrait
PORTRAIT_CENTRE_X = 88    # icon x (of 256) put in the middle of the portrait: between the eyes, over the hand
PHOTO_CENTRE_X = 118      # the backpack photo is nearly square, so it shows more of the body
PORTRAIT_CORNER = 56      # the icon tile's rounded bottom corners clip the body: refilled within this square
PORTRAIT_EYES = ((57, 74), (120, 59))  # icon px, for the nightmare variants


def thinking_frog(fill_corners=False):
    """The thinking frog cut from its app-icon tile. The white tile has a faint grey outline, so every large
    light patch is background; the edge is pulled in one pixel (the icon's white anti-aliasing shows as a rim
    when upscaled). The body runs off the tile's bottom edge, whose last two rows are blended with the outline,
    so the row above is repeated there. The tile's rounded bottom corners leave the body curving in, which
    reads as its own contour; fill_corners would inpaint them instead."""
    import cv2
    from frog_parts import defringe
    src = np.asarray(Image.open(PORTRAIT_SRC).convert("RGB")).copy()
    src[-2:] = src[-3]
    f = src.astype(np.float32)
    mx, mn = f.max(axis=2), f.min(axis=2)
    light = (f.mean(axis=2) > 200) & ((mx - mn) / np.maximum(mx, 1.0) < 0.10)
    n, lab, st, _ = cv2.connectedComponentsWithStats(light.astype(np.uint8), connectivity=8)
    bg = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 300])
    mask = largest(~bg)
    # where the frog runs off the icon's edge it must stay cut straight, so the border is not eroded
    mask = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8), borderType=cv2.BORDER_REPLICATE) > 0
    h, w = mask.shape
    hole = np.zeros_like(mask)
    if fill_corners:
        hole[h - PORTRAIT_CORNER:, :PORTRAIT_CORNER] = True
        hole[h - PORTRAIT_CORNER:, w - PORTRAIT_CORNER:] = True
    hole &= ~mask
    rgb = cv2.inpaint(np.where(mask[..., None], src, 0).astype(np.uint8), (~mask).astype(np.uint8), 7,
                      cv2.INPAINT_TELEA)
    mask |= hole
    alpha = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 0.7) * mask
    rgba = np.dstack([np.where(hole[..., None], rgb, src), (alpha * 255).astype(np.uint8)])
    return Image.fromarray(defringe(rgba), "RGBA")


def portrait(size, variant, frog, centre_x=PORTRAIT_CENTRE_X):
    """size (w, h) portrait: a close-up of the frog (head, hand on chin, top of the belly) on a dark painted
    backdrop like the game's portraits; the icon's cut-off left, right and bottom edges fall outside the frame.
    centre_x is the icon x put in the middle (wider frames show more of the frog)."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    glow = np.exp(-(((xx - w * 0.55) / (w * 0.6)) ** 2 + ((yy - h * 0.35) / (h * 0.45)) ** 2))
    rng = np.random.default_rng(7)
    base = np.array([16.0, 14.0, 13.0]) + glow[..., None] * np.array([34.0, 30.0, 26.0])
    base += rng.normal(0, 2.5, (h, w, 1))
    bg = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    scale = h / frog.height
    x0 = round(centre_x * scale - w / 2)
    big = frog.resize((round(frog.width * scale), h), Image.LANCZOS)
    if scale > 2:  # the source is only 256 px: crisp the upscaled colour a little, keep the edge as it is
        rgb = big.convert("RGB").filter(ImageFilter.UnsharpMask(radius=round(scale), percent=70, threshold=2))
        rgb.putalpha(big.getchannel("A"))
        big = rgb
    layer = big.crop((x0, 0, x0 + w, h))
    if variant in ("Inner", "bleeding", "bleeding2"):  # flat-painted nightmare versions, on a flat backdrop
        flat = ImageOps.posterize(layer.convert("RGB"), 3).filter(ImageFilter.ModeFilter(5)).convert("RGBA")
        flat.putalpha(layer.getchannel("A"))
        layer = flat
        bg = Image.new("RGBA", size, (34, 28, 26, 255))
    bg.alpha_composite(layer)
    out = bg.convert("RGB")
    if variant in ("Disappear_1", "Disappear_2"):     # the face fading out: blurred and dark
        k = 1 if variant == "Disappear_1" else 2
        out = out.filter(ImageFilter.BoxBlur(4 * k)).filter(ImageFilter.GaussianBlur(3 * k))
        out = Image.blend(Image.new("RGB", size, (10, 9, 8)), out, 0.65 if k == 1 else 0.4)
    elif variant in ("Inner", "bleeding", "bleeding2"):
        if variant.startswith("bleeding"):
            d = ImageDraw.Draw(out)
            for i, (ex, ey) in enumerate(PORTRAIT_EYES):
                x, y = ex * scale - x0, (ey + 12) * scale
                for dx, ln in ((-4, 50), (0, 80), (5, 40)) if variant == "bleeding2" else ((0, 45),):
                    d.line([(x + dx, y), (x + dx * 1.5, y + ln * scale * (1.0 - 0.2 * i))], fill=(120, 18, 16),
                           width=max(2, round(3 * scale)))
    return out


def build_portraits(out_path):
    env = UnityPy.load(source_bundle(PORTRAITS))
    by = {o.path_id: o for o in env.objects}
    frog = thinking_frog()
    done = []
    for o in env.objects:
        if o.type != ClassIDType.Sprite:
            continue
        name = o.peek_name()
        if not name.startswith("portrait_Player"):
            continue
        s = o.read_typetree()
        tex = by[s["m_RD"]["texture"]["m_PathID"]].read()
        rect = s["m_Rect"]
        if (rect["x"], rect["y"], rect["width"], rect["height"]) != (0.0, 0.0, tex.m_Width, tex.m_Height):
            raise ValueError(f"{name}: sprite is not the whole texture")
        variant = name[len("portrait_Player"):].lstrip("_")
        tex.set_image(portrait((tex.m_Width, tex.m_Height), variant, frog), target_format=TextureFormat.RGB24)
        tex.save()
        done.append(name)
    with open(out_path, "wb") as f:
        f.write(env.file.save(packer="lz4"))
    print(f"portraits: {len(done)} replaced ({', '.join(sorted(done))}) -> {out_path}")


def build_status_photo(out_path):
    """The protagonist's photo on the backpack (status) page, inside a polaroid: Assets/UI/Health/fine.png."""
    env = UnityPy.load(source_bundle(STATUS))
    by = {o.path_id: o for o in env.objects}
    sprite = next(o for o in env.objects if o.type == ClassIDType.Sprite and o.peek_name() == STATUS_PHOTO)
    s = sprite.read_typetree()
    tex = by[s["m_RD"]["texture"]["m_PathID"]].read()
    rect = s["m_Rect"]
    if (rect["x"], rect["y"], rect["width"], rect["height"]) != (0.0, 0.0, tex.m_Width, tex.m_Height):
        raise ValueError(f"{STATUS_PHOTO}: sprite is not the whole texture")
    tex.set_image(portrait((tex.m_Width, tex.m_Height), "", thinking_frog(), PHOTO_CENTRE_X),
                  target_format=TextureFormat.RGB24)
    tex.save()
    with open(out_path, "wb") as f:
        f.write(env.file.save(packer="lz4"))
    print(f"backpack photo: {STATUS_PHOTO} {tex.m_Width}x{tex.m_Height} replaced -> {out_path}")


# ---------------------------------------------------------------- Unity audio
def build_audio_switch(out_path):
    """globalgamemanagers with AudioManager.m_DisableAudio cleared: one byte, located by re-serializing."""
    src = BACKUP_GGM if os.path.exists(BACKUP_GGM) else os.path.join(GAME, GGM)
    data = bytearray(open(src, "rb").read())
    env = UnityPy.load(src)
    am = next(o for o in env.objects if o.type == ClassIDType.AudioManager)
    tree = am.read_typetree()
    old = am.get_raw_data()
    if bytes(data[am.byte_start:am.byte_start + am.byte_size]) != old:
        raise ValueError("AudioManager is not where the file header says")
    if not tree["m_DisableAudio"]:
        raise ValueError("Unity audio is already enabled in " + src)
    tree["m_DisableAudio"] = False
    w = EndianBinaryWriter(endian=am.reader.endian)
    TypeTreeHelper.write_typetree(tree, am._get_typetree_node(), w, am.assets_file)
    diff = [i for i, (a, b) in enumerate(zip(old, w.bytes)) if a != b]
    if len(w.bytes) != len(old) or len(diff) != 1:
        raise ValueError("unexpected AudioManager layout")
    data[am.byte_start + diff[0]] = w.bytes[diff[0]]
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"Unity audio enabled: AudioManager.m_DisableAudio at file offset {am.byte_start + diff[0]} -> {out_path}")


def main():
    build = sys.argv[1]
    patches = os.path.join(build, "patches")
    os.makedirs(patches, exist_ok=True)
    built = [PORTRAITS, STATUS]
    if os.path.exists(LAUGH_DIR + "/laugh.json"):
        build_clips(os.path.join(patches, CLIPS))
        build_audio_switch(os.path.join(build, "globalgamemanagers"))
        built.append(CLIPS)
    else:  # the frames come from a video that is not in the repository (see laugh_frames.py)
        print(f"no {LAUGH_DIR}/laugh.json: idle laugh and its sound skipped")
    build_portraits(os.path.join(patches, PORTRAITS))
    build_status_photo(os.path.join(patches, STATUS))
    listing = os.path.join(patches, "bundles.txt")
    names = open(listing, encoding="utf-8").read().split() if os.path.exists(listing) else []
    names += [fn for fn in built if fn not in names]
    with open(listing, "w", encoding="utf-8") as f:
        f.write("".join(fn + "\n" for fn in names))
    print(f"bundles.txt: {len(names)} bundles")


if __name__ == "__main__":
    main()
