"""Check what frog_extras.py built by reading it back: the laugh clip's frame order and length, the sprites, the
sound (decoded through the bundle's .resource node with FMOD), the edited PlayMaker template, the preload table
(only the template's range may change) and that no other original object changed; the dialogue portraits and the
health / difficulty photos (only their textures change); the new-game page's photo scale (one byte); the audio
flag.

usage: python -P -E verify_extras.py <build_dir> [<preview_dir>]
"""
import os
import sys

import UnityPy
from UnityPy.enums import ClassIDType

sys.path.insert(0, os.path.dirname(__file__))
from clip_curves import decode  # noqa: E402
from frog_extras import (BACKUP_GGM, CLIPS, GAME, GGM, LAUGH_STATE, PHOTOS, PORTRAITS, SYSTEM_MENU,  # noqa: E402
                         TEMPLATE, action_params, stable_id)
from frogify import source_bundle  # noqa: E402


def check_clips(path, preview):
    env = UnityPy.load(path)
    by = {o.path_id: o for o in env.objects}
    print("nodes:", [(n, f.flags) for n, f in env.file.files.items()])
    clip = by[stable_id("Player_FrogLaugh")].read_typetree()
    curves, stop = decode(clip)
    mapping = clip["m_ClipBindingConstant"]["pptrCurveMapping"]
    names = [by[mapping[int(c[3])]["m_PathID"]].read().m_Name for _, c in curves[3]]
    n = len(mapping)
    ok = names == [f"FrogLaugh{i:03d}" for i in range(1, n)]   # frame 0 comes from the -FLT_MAX sentinel
    print(f"clip {clip['m_Name']}: {n} frames, {stop:.2f}s, order {'OK' if ok else 'WRONG'}")
    if preview:
        for i in (0, n // 3, 2 * n // 3, n - 1):
            by[stable_id(f"FrogLaugh{i:03d}")].read().image.save(os.path.join(preview, f"laugh_{i:03d}.png"))
    audio = by[stable_id("FrogLaugh.audio")].read()
    wav = next(iter(audio.samples.values()))
    print(f"sound {audio.m_Name}: {audio.m_Length:.2f}s, {audio.m_Channels} ch, {audio.m_Frequency} Hz, "
          f"FMOD decodes {len(wav)} bytes of WAV")
    tpl = by[TEMPLATE].read_typetree()
    states = {s["name"]: s for s in tpl["fsm"]["states"]}
    loop = states["NormalLoop"]
    print("NormalLoop wait:", [round(p["value"], 2) for p in loop["actionData"]["fsmFloatParams"][2:4]],
          "Trigger ->", [t["toState"] for t in loop["transitions"] if t["fsmEvent"]["name"] == "Trigger"])
    ad = states[LAUGH_STATE]["actionData"]
    for i, name in enumerate(ad["actionNames"]):
        print(f"  {LAUGH_STATE}: {name} #{ad['actionHashCodes'][i]} {sorted(action_params(ad, i))}")
    orig = UnityPy.load(source_bundle(CLIPS))
    oab = next(o for o in orig.objects if o.type == ClassIDType.AssetBundle).read_typetree()
    nab = next(o for o in env.objects if o.type == ClassIDType.AssetBundle).read_typetree()
    moved = 0
    for (_, oi), (_, ni) in zip(oab["m_Container"], nab["m_Container"]):
        a = oab["m_PreloadTable"][oi["preloadIndex"]:oi["preloadIndex"] + oi["preloadSize"]]
        b = nab["m_PreloadTable"][ni["preloadIndex"]:ni["preloadIndex"] + ni["preloadSize"]]
        if oi["asset"]["m_PathID"] == TEMPLATE:
            unresolved = [p for p in b[len(a):] if p["m_PathID"] not in by]
            print(f"template preload range +{len(b) - len(a)} objects, prefix kept {b[:len(a)] == a}, "
                  f"unresolved {len(unresolved)}")
        elif a != b:
            moved += 1
    changed = [by[o.path_id].type.name for o in orig.objects if o.get_raw_data() != by[o.path_id].get_raw_data()]
    print(f"other preload ranges changed: {moved}; original objects changed: {sorted(changed)}")


def check_textures(path, fn, preview):
    env = UnityPy.load(path)
    orig = {o.path_id: o for o in UnityPy.load(source_bundle(fn)).objects}
    changed = [o for o in env.objects if o.get_raw_data() != orig[o.path_id].get_raw_data()]
    print(f"{fn}: {len(changed)} objects changed {sorted(set(o.type.name for o in changed))}: "
          f"{sorted(o.read().m_Name for o in changed)}")
    if preview:
        for o in changed:
            o.read().image.save(os.path.join(preview, o.read().m_Name + ".png"))


def check_scene(path, fn):
    """Every object of every serialized file byte for byte, except the new-game photo's RectTransform."""
    new, orig = UnityPy.load(path), UnityPy.load(source_bundle(fn))
    for name, f in orig.file.files.items():
        if not hasattr(f, "objects"):
            continue
        g = new.file.files[name]
        for pid, o in f.objects.items():
            a, b = o.get_raw_data(), g.objects[pid].get_raw_data()
            if a != b:
                diff = [(i, a[i], b[i]) for i in range(min(len(a), len(b))) if a[i] != b[i]]
                print(f"{fn}: {o.type.name} {pid} changed {diff}, m_LocalScale "
                      f"{g.objects[pid].read_typetree().get('m_LocalScale')}")
        if set(f.objects) != set(g.objects):
            print(f"{fn}: object set differs in {name}")


def check_audio_switch(path):
    src = BACKUP_GGM if os.path.exists(BACKUP_GGM) else os.path.join(GAME, GGM)
    a, b = open(src, "rb").read(), open(path, "rb").read()
    diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    am = next(o for o in UnityPy.load(path).objects if o.type == ClassIDType.AudioManager).read_typetree()
    print(f"globalgamemanagers: same size {len(a) == len(b)}, bytes changed {diff}, "
          f"m_DisableAudio {am['m_DisableAudio']}")


def main():
    build = sys.argv[1]
    preview = sys.argv[2] if len(sys.argv) > 2 else None
    if preview:
        os.makedirs(preview, exist_ok=True)
    clips = os.path.join(build, "patches", CLIPS)
    if os.path.exists(clips):
        check_clips(clips, preview)
        check_audio_switch(os.path.join(build, "globalgamemanagers"))
    for fn in [PORTRAITS] + [fn for _, fn, _, _ in PHOTOS]:
        check_textures(os.path.join(build, "patches", fn), fn, preview)
    check_scene(os.path.join(build, "patches", SYSTEM_MENU), SYSTEM_MENU)


if __name__ == "__main__":
    main()
