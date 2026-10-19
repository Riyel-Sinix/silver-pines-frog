"""Build the complete frog mod for one game version and write its installer manifest.

usage: python -P -E scripts/build_frog.py --game GAME [--output frogmod/build]
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))


def write_manifest(build):
    import UnityPy
    from game_paths import AA_REL, GAME_PATH, MAIN, game_identity, sha256, source_file

    pairs = [(MAIN, f"{AA_REL}/{MAIN}")]
    listing = (build / "patches/bundles.txt").read_text(encoding="utf-8").splitlines()
    for name in listing:
        if not name or Path(name).name != name or not name.endswith(".bundle"):
            raise ValueError(f"Invalid patch name: {name!r}")
        pairs.append((f"patches/{name}", f"{AA_REL}/{name}"))
    if len(set(listing)) != len(listing):
        raise ValueError("Duplicate patch names")
    if (build / "globalgamemanagers").is_file():
        pairs.append(("globalgamemanagers", "Carpenter_Data/globalgamemanagers"))
    env = UnityPy.load(source_file("Carpenter_Data/globalgamemanagers"))
    unity_version = str(next(iter(env.objects)).assets_file.unity_version)
    steam_manifest = GAME_PATH.parent.parent / "appmanifest_2333000.acf"
    steam_build = None
    if steam_manifest.is_file():
        match = re.search(r'"buildid"\s+"(\d+)"', steam_manifest.read_text(encoding="utf-8"))
        steam_build = match.group(1) if match else None
    data = {"schema_version": 1,
            "game": {**game_identity(), "unity_version": unity_version, "steam_build_id": steam_build},
            "files": [{"game_path": game_rel, "build_path": built_rel,
                       "source_sha256": sha256(source_file(game_rel)),
                       "output_sha256": sha256(build / built_rel)} for built_rel, game_rel in pairs]}
    (build / "manifest.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: Steam build {steam_build}, Unity {unity_version}, {len(pairs)} files", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game")
    parser.add_argument("--output", default="frogmod/build")
    parser.add_argument("--dump", default="_dump")
    parser.add_argument("--reuse-index", action="store_true", help="reuse indices only if their game identity matches")
    args = parser.parse_args()
    if args.game:
        os.environ["SILVER_PINES"] = str(Path(args.game).resolve())
    os.environ["SILVER_PINES_DUMP"] = str(Path(args.dump).resolve())
    from game_paths import DUMP, GAME_PATH, MAIN, ROOT, assert_original_assets, index_identity
    if not (GAME_PATH / "Carpenter.exe").is_file():
        parser.error(f"Game not found: {GAME_PATH}")
    build = Path(args.output).resolve()
    if build.exists() and any(build.iterdir()):
        parser.error(f"Output directory is not empty; use a new directory: {build}")
    version_file = DUMP / "game-version.json"
    if args.reuse_index:
        if not version_file.is_file() or json.loads(version_file.read_text(encoding="utf-8")) != index_identity():
            parser.error("Indices belong to a different game version; omit --reuse-index to rescan")
        assert_original_assets()
    else:
        from refresh_game_data import refresh
        refresh()
    build.mkdir(parents=True, exist_ok=True)
    for script, parameters in (
        ("frogify.py", ["main", build / MAIN]),
        ("frogify.py", ["patches", build / "patches"]),
        ("frog_extras.py", [build]),
    ):
        subprocess.run([sys.executable, "-P", "-E", str(ROOT / "scripts" / script), *map(str, parameters)], check=True)
    write_manifest(build)


if __name__ == "__main__":
    main()
