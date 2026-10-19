"""Resolve this game's original files without mixing in backups from another release."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AA_REL = "Carpenter_Data/StreamingAssets/aa/StandaloneWindows64"
METADATA_REL = "Carpenter_Data/il2cpp_data/Metadata/global-metadata.dat"
MAIN = "team17_auto_base_characters_compressed_assets_player.bundle"


def find_game():
    explicit = os.environ.get("SILVER_PINES")
    if explicit:
        return Path(explicit).resolve()
    candidates = [Path("D:/SteamLibrary/steamapps/common/Silver Pines"), Path("D:/Games/Silver Pines")]
    for drive in ("C", "D", "E", "F"):
        candidates.append(Path(f"{drive}:/Program Files (x86)/Steam/steamapps/common/Silver Pines"))
    return next((p for p in candidates if (p / "Carpenter.exe").is_file()), candidates[0])


GAME_PATH = find_game()
GAME = GAME_PATH.as_posix()
AA = (GAME_PATH / AA_REL).as_posix()
DUMP = Path(os.environ.get("SILVER_PINES_DUMP", ROOT / "_dump"))


@lru_cache(maxsize=None)
def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@lru_cache(maxsize=1)
def game_identity():
    return {"gameassembly_sha256": sha256(GAME_PATH / "GameAssembly.dll"),
            "metadata_sha256": sha256(GAME_PATH / METADATA_REL)}


def index_identity():
    return {**game_identity(),
            "catalog_sha256": sha256(GAME_PATH / "Carpenter_Data/StreamingAssets/aa/catalog.bin")}


@lru_cache(maxsize=1)
def original_backups():
    """Only installer manifests bound to this installation and its current code qualify."""
    found = {}
    for manifest_path in sorted((ROOT / "frogmod/backup/versions").glob("*/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if os.path.normcase(os.path.abspath(data.get("game_path", ""))) != os.path.normcase(str(GAME_PATH)):
            continue
        if any(data.get("game", {}).get(k, "").lower() != v for k, v in game_identity().items()):
            continue
        for entry in data["files"]:
            path = manifest_path.parent / entry["game_path"]
            installed = GAME_PATH / entry["game_path"]
            if (path.is_file() and installed.is_file()
                    and sha256(path) == entry["source_sha256"].lower()
                    and sha256(installed) in (entry["source_sha256"].lower(), entry["output_sha256"].lower())):
                found[entry["game_path"]] = path
    return found


def source_file(relative):
    return str(original_backups().get(relative, GAME_PATH / relative))


def source_bundle(name):
    return source_file(f"{AA_REL}/{name}")


def assert_original_assets():
    """Refuse to draw over an installed frog when no verified original backup is available."""
    import UnityPy
    env = UnityPy.load(source_bundle("team17_auto_base_characters_assets_player.bundle"))
    if any(o.type.name == "AnimationClip" and o.peek_name() == "Player_FrogLaugh" for o in env.objects):
        raise ValueError("The source contains an installed frog mod. Restore original game files or provide "
                         "the verified backup for this installation before rebuilding.")
    del env
    env = UnityPy.load(source_bundle(MAIN))
    idle = next(o for o in env.objects if o.type.name == "Sprite" and o.peek_name() == "PlayerIdle00")
    if idle.read_typetree()["m_RD"]["m_VertexData"]["m_VertexCount"] == 4:
        raise ValueError("PlayerIdle00 is already redrawn. A verified original backup is required.")


def resolve_bundle(name):
    """Content hashes in Addressables patch names can change between releases."""
    if (GAME_PATH / AA_REL / name).is_file():
        return name
    import re
    stem = re.sub(r"_[0-9a-f]{32}\.bundle$", "_", name)
    candidates = sorted(p.name for p in (GAME_PATH / AA_REL).glob(stem + "*.bundle")) if stem != name else []
    if len(candidates) != 1:
        raise ValueError(f"Cannot resolve bundle {name}: {candidates}")
    return candidates[0]
