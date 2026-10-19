"""Regenerate version-dependent sprite and animation indices from the selected game.

usage: python -P -E scripts/refresh_game_data.py [--game GAME] [--dump DIRECTORY]
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))


def refresh():
    import UnityPy
    from game_paths import AA, DUMP, ROOT, assert_original_assets, index_identity, source_bundle

    assert_original_assets()
    DUMP.mkdir(parents=True, exist_ok=True)
    (DUMP / "game-version.json").unlink(missing_ok=True)
    sprites, clips = [], []
    files = sorted(Path(AA).glob("*.bundle"))
    for index, path in enumerate(files):
        env = UnityPy.load(source_bundle(path.name))
        hits, animations = [], []
        for obj in env.objects:
            kind = obj.type.name
            if kind == "Sprite" and path.name.startswith("team17_auto_patch"):
                tree = obj.read_typetree()
                rect = tree["m_Rect"]
                hits.append(f"{tree['m_Name']}({rect['width']:g}x{rect['height']:g}@{tree['m_PixelsToUnits']:g})")
            elif kind in ("AnimationClip", "AnimatorController", "AnimatorOverrideController"):
                animations.append(f"{kind[:5]}:{obj.peek_name()}")
        if hits:
            sprites.append(f"{path.name} {hits!r}\n")
        if animations:
            clips.append(f"{path.name}  ({len(animations)})  {animations!r}\n")
        if (index + 1) % 400 == 0:
            print(f"scanned {index + 1}/{len(files)} bundles", flush=True)
    (DUMP / "patch_bundle_sprites.txt").write_text("".join(sprites), encoding="utf-8")
    (DUMP / "scan_clips.txt").write_text("".join(clips), encoding="utf-8")
    for script, args in (
        ("scan_sprite_clips.py", [DUMP / "all_player_clips.txt"]),
        ("clip_map.py", [DUMP / "clip_map.txt"]),
        ("clip_curves.py", [DUMP / "sprite_nodes.json"]),
    ):
        subprocess.run([sys.executable, "-P", "-E", str(ROOT / "scripts" / script), *map(str, args)], check=True)
    (DUMP / "game-version.json").write_text(json.dumps(index_identity(), indent=2) + "\n", encoding="utf-8")
    print(f"Refreshed indices for {len(files)} bundles in {DUMP}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game")
    parser.add_argument("--dump")
    args = parser.parse_args()
    if args.game:
        os.environ["SILVER_PINES"] = str(Path(args.game).resolve())
    if args.dump:
        os.environ["SILVER_PINES_DUMP"] = str(Path(args.dump).resolve())
    refresh()
