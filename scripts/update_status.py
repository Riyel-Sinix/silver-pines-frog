"""After a game update: classify every file the frog mod replaces by comparing the installed file with the
build manifest's original (source) and modded (output) hashes.

usage: python -P -E scripts/update_status.py [game_dir] [out.json]

  modded    installed file == our output (the update did not touch it)
  original  installed file == the old original (mod not installed there)
  changed   neither: the update shipped a new official file (rebuild from it)
  missing   file gone from the game
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
game = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\SteamLibrary\steamapps\common\Silver Pines")
out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
manifest = json.loads((ROOT / "frogmod/build/manifest.json").read_text(encoding="utf-8"))


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


rows = []
counts = {}
for entry in manifest["files"]:
    path = game / entry["game_path"]
    if not path.is_file():
        state, digest = "missing", None
    else:
        digest = sha256(path)
        state = ("modded" if digest == entry["output_sha256"] else
                 "original" if digest == entry["source_sha256"] else "changed")
    counts[state] = counts.get(state, 0) + 1
    rows.append({"game_path": entry["game_path"], "state": state, "sha256": digest})
    if state in ("changed", "missing"):
        print(state, entry["game_path"])
print(counts)
for name in ("GameAssembly.dll", "Carpenter_Data/il2cpp_data/Metadata/global-metadata.dat"):
    print(name, sha256(game / name))
if out:
    out.write_text(json.dumps({"counts": counts, "files": rows}, indent=1), encoding="utf-8")
