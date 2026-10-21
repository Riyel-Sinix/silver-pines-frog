#!/usr/bin/env python3
"""Install or restore the Silver Pines frog mod in a Proton game directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid


MOD_ROOT = Path(__file__).resolve().parent
BUILD_PREFIX = "build/"
BUNDLE_PREFIX = "Carpenter_Data/StreamingAssets/aa/StandaloneWindows64/"
METADATA_PATH = "Carpenter_Data/il2cpp_data/Metadata/global-metadata.dat"
MAIN_BUNDLE = "team17_auto_base_characters_compressed_assets_player.bundle"
HASH_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class ModError(Exception):
    """A validation or filesystem error safe to show to the user."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ModError(f"Cannot read required file: {path}: {exc}") from exc
    return digest.hexdigest()


def _relative_parts(relative: str) -> tuple[str, ...]:
    if not isinstance(relative, str) or not relative.strip():
        raise ModError(f"Invalid relative path: {relative!r}")
    normalized = relative.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ModError(f"Absolute path is not allowed: {relative}")
    parts = tuple(normalized.split("/"))
    if any(part in ("", ".", "..") or "\x00" in part for part in parts):
        raise ModError(f"Invalid relative path: {relative}")
    return parts


def safe_path(root: Path, relative: str) -> Path:
    """Return a lexical path only after resolving symlinks within the root."""
    parts = _relative_parts(relative)
    resolved_root = root.resolve()
    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ModError(f"Path escapes its allowed directory: {relative}") from exc
    return candidate


def require_regular_file(path: Path, description: str, *, reject_symlink: bool = False) -> None:
    try:
        if reject_symlink and path.is_symlink():
            raise ModError(f"Refusing symlink for {description}: {path}")
        if not path.is_file():
            raise ModError(f"Missing {description}: {path}")
    except OSError as exc:
        raise ModError(f"Cannot inspect {description}: {path}: {exc}") from exc


def canonical_game_path(path: Path) -> Path:
    try:
        game = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ModError(f"Game directory does not exist: {path}") from exc
    if not game.is_dir():
        raise ModError(f"Game directory is not a directory: {game}")
    try:
        executable = safe_path(game, "Carpenter.exe")
        data_dir = safe_path(game, "Carpenter_Data")
    except ModError as exc:
        raise ModError(f"Not the Windows Proton build: {game}") from exc
    if not executable.is_file():
        raise ModError(f"Not the Windows Proton build (Carpenter.exe missing): {game}")
    if not data_dir.is_dir():
        raise ModError(f"Not the Windows Proton build (Carpenter_Data missing): {game}")
    return game


def _library_candidates() -> list[Path]:
    home = Path.home()
    roots = [home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"]
    libraries: list[Path] = []
    seen: set[str] = set()

    def add_library(raw: str | Path) -> None:
        path = Path(raw).expanduser()
        if path.name == "steamapps":
            path = path.parent
        try:
            key = os.path.normcase(str(path.resolve(strict=False)))
        except (OSError, RuntimeError):
            key = os.path.normcase(str(path.absolute()))
        if key not in seen:
            seen.add(key)
            libraries.append(path)

    for root in roots:
        add_library(root)
    # Read every discovered library file; a secondary library may itself list others.
    cursor = 0
    while cursor < len(libraries):
        library = libraries[cursor]
        cursor += 1
        vdf = library / "steamapps" / "libraryfolders.vdf"
        try:
            content = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s*"([^"]+)"|"\d+"\s*"([^"]+)"', content):
            raw = match.group(1) or match.group(2)
            add_library(raw.replace("\\\\", "\\"))
    return [library / "steamapps/common/Silver Pines" for library in libraries]


def find_game_directory(explicit: str | None) -> Path:
    raw = explicit or os.environ.get("SILVER_PINES")
    if raw:
        candidate = Path(raw.strip('"')).expanduser()
        if candidate.name.lower() == "carpenter.exe":
            candidate = candidate.parent
        return canonical_game_path(candidate)
    for candidate in _library_candidates():
        try:
            return canonical_game_path(candidate)
        except ModError:
            continue
    raise ModError(
        "Could not find Silver Pines in Steam libraries. Pass a game directory with "
        "--game-directory or as the optional path argument."
    )


def assert_game_not_running() -> None:
    if not sys.platform.startswith("linux"):
        return
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return
    own_pid = os.getpid()
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        for argument in arguments:
            if not argument:
                continue
            name = argument.decode("utf-8", errors="ignore").replace("\\", "/").rsplit("/", 1)[-1]
            if name.casefold() == "carpenter.exe":
                raise ModError("Silver Pines is running. Exit the game before installing or restoring.")


def read_manifest(path: Path) -> dict:
    require_regular_file(path, "build manifest")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModError(f"Cannot read manifest: {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ModError(f"Unsupported manifest schema: {path}")
    if "backup_layout" in manifest and manifest["backup_layout"] != "sha256-v1":
        raise ModError(f"Unsupported backup layout: {manifest['backup_layout']!r}")
    game = manifest.get("game")
    if not isinstance(game, dict):
        raise ModError("Manifest has no game identity")
    for field in ("gameassembly_sha256", "metadata_sha256"):
        if not isinstance(game.get(field), str) or not HASH_PATTERN.fullmatch(game[field]):
            raise ModError(f"Manifest has an invalid game hash: {field}")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ModError("Manifest has no resource files")

    seen_game: set[str] = set()
    seen_build: set[str] = set()
    has_main = False
    for item in files:
        if not isinstance(item, dict):
            raise ModError("Manifest contains an invalid file entry")
        game_relative = item.get("game_path")
        build_relative = item.get("build_path")
        _relative_parts(game_relative)
        _relative_parts(build_relative)
        game_relative = game_relative.replace("\\", "/")
        build_relative = build_relative.replace("\\", "/")
        is_bundle = (game_relative.startswith(BUNDLE_PREFIX) and
                     re.fullmatch(r"[^/]+\.bundle", game_relative[len(BUNDLE_PREFIX):], re.IGNORECASE))
        if not is_bundle and game_relative != "Carpenter_Data/globalgamemanagers":
            raise ModError(f"Unsupported game resource path: {game_relative}")
        if is_bundle:
            bundle_name = game_relative[len(BUNDLE_PREFIX):]
            allowed_builds = {bundle_name, f"patches/{bundle_name}"}
            has_main |= bundle_name.casefold() == MAIN_BUNDLE.casefold()
        else:
            allowed_builds = {"globalgamemanagers"}
        if build_relative not in allowed_builds:
            raise ModError(f"Build path does not match game resource: {build_relative}")
        if game_relative in seen_game or build_relative in seen_build:
            raise ModError("Manifest contains duplicate resource paths")
        seen_game.add(game_relative)
        seen_build.add(build_relative)
        for field in ("source_sha256", "output_sha256"):
            if not isinstance(item.get(field), str) or not HASH_PATTERN.fullmatch(item[field]):
                raise ModError(f"Invalid {field} for {game_relative}")
    if not has_main:
        raise ModError("Manifest is missing the main character bundle")
    return manifest


def manifest_file_list(manifest: dict) -> list[dict]:
    return [{key: item[key] for key in ("game_path", "build_path", "source_sha256", "output_sha256")}
            for item in manifest["files"]]


def backup_relative_path(manifest: dict, item: dict) -> str:
    if "backup_layout" not in manifest:
        return item["game_path"]
    if manifest["backup_layout"] != "sha256-v1":
        raise ModError(f"Unsupported backup layout: {manifest['backup_layout']!r}")
    return "files/" + item["source_sha256"].lower() + ".bin"


def assert_game_version(manifest: dict, game_root: Path) -> None:
    assembly = safe_path(game_root, "GameAssembly.dll")
    metadata = safe_path(game_root, METADATA_PATH)
    require_regular_file(assembly, "GameAssembly.dll", reject_symlink=True)
    require_regular_file(metadata, "IL2CPP metadata")
    if (sha256(assembly) != manifest["game"]["gameassembly_sha256"].lower() or
            sha256(metadata) != manifest["game"]["metadata_sha256"].lower()):
        raise ModError("Game version does not match this build or backup")


def build_relative_path(relative: str) -> str:
    return BUILD_PREFIX + relative.replace("\\", "/")


def assert_build(manifest: dict) -> None:
    for item in manifest["files"]:
        path = safe_path(MOD_ROOT, build_relative_path(item["build_path"]))
        require_regular_file(path, "built resource")
        if sha256(path) != item["output_sha256"].lower():
            raise ModError(f"Built resource hash mismatch: {path}")

    listed_path = safe_path(MOD_ROOT, "build/patches/bundles.txt")
    require_regular_file(listed_path, "patch bundle list")
    try:
        listed = [line.strip() for line in listed_path.read_text(encoding="utf-8-sig").splitlines()
                  if line.strip()]
    except OSError as exc:
        raise ModError(f"Cannot read patch bundle list: {exc}") from exc
    if len(set(listed)) != len(listed):
        raise ModError("Patch bundle list contains duplicates")
    expected = [item["build_path"].replace("\\", "/")[len("patches/"):]
                for item in manifest["files"]
                if item["build_path"].replace("\\", "/").startswith("patches/")]
    if set(listed) != set(expected) or len(listed) != len(expected):
        raise ModError("Patch bundle list does not exactly match the manifest")


def assert_targets(manifest: dict, game_root: Path) -> None:
    for item in manifest["files"]:
        target = safe_path(game_root, item["game_path"])
        require_regular_file(target, "game resource", reject_symlink=True)
        actual = sha256(target)
        if actual not in (item["source_sha256"].lower(), item["output_sha256"].lower()):
            raise ModError(f"Game resource does not match source or this mod version: {target}")


def _same_game_path(saved: object, game_root: Path) -> bool:
    if not isinstance(saved, str) or not Path(saved).is_absolute():
        return False
    try:
        saved_path = Path(saved).resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return os.path.normcase(str(saved_path)) == os.path.normcase(str(game_root))


def backup_key(manifest_path: Path, manifest: dict, game_root: Path) -> str:
    path_identity = str(game_root).lower() if os.name == "nt" else str(game_root)
    path_hash = hashlib.sha256(path_identity.encode("utf-8")).hexdigest()[:8]
    return (manifest["game"]["gameassembly_sha256"][:16].lower() + "-" +
            sha256(manifest_path)[:12] + "-" + path_hash)


def _backup_manifest(manifest: dict, game_root: Path) -> dict:
    saved = dict(manifest)
    saved["game"] = dict(manifest["game"])
    saved["files"] = [dict(item) for item in manifest["files"]]
    saved["backup_layout"] = "sha256-v1"
    saved["game_path"] = str(game_root)
    saved["created_at"] = datetime.now(timezone.utc).isoformat()
    return saved


def _assert_backup(manifest: dict, backup_root: Path, game_root: Path) -> None:
    if not _same_game_path(manifest.get("game_path"), game_root):
        raise ModError("Backup belongs to a different game directory")
    assert_game_version(manifest, game_root)
    for item in manifest["files"]:
        backup_path = safe_path(backup_root, backup_relative_path(manifest, item))
        require_regular_file(backup_path, "original backup")
        if sha256(backup_path) != item["source_sha256"].lower():
            raise ModError(f"Original backup hash mismatch: {backup_path}")


def create_backup(manifest_path: Path, manifest: dict, game_root: Path) -> Path:
    key = backup_key(manifest_path, manifest, game_root)
    final_relative = f"backup/versions/{key}"
    final_root = safe_path(MOD_ROOT, final_relative)
    if final_root.exists():
        saved_path = safe_path(MOD_ROOT, f"{final_relative}/manifest.json")
        saved = read_manifest(saved_path)
        _assert_backup(saved, final_root, game_root)
        if manifest_file_list(saved) != manifest_file_list(manifest):
            raise ModError("Existing backup manifest does not match this build")
        return final_root

    pending_relative = f"backup/versions/{key}.pending-{uuid.uuid4().hex}"
    pending_root = safe_path(MOD_ROOT, pending_relative)
    backup_manifest = _backup_manifest(manifest, game_root)
    try:
        pending_root.mkdir(parents=True)
        for item in manifest["files"]:
            source = safe_path(game_root, item["game_path"])
            backup = safe_path(pending_root, backup_relative_path(backup_manifest, item))
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, backup)
            if sha256(backup) != item["source_sha256"].lower():
                raise ModError(f"Original backup verification failed: {backup}")
        manifest_out = safe_path(pending_root, "manifest.json")
        manifest_out.write_text(json.dumps(backup_manifest, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        os.replace(pending_root, final_root)
    except Exception:
        if pending_root.exists():
            shutil.rmtree(pending_root, ignore_errors=True)
        raise
    return final_root


def _transaction(manifest: dict, game_root: Path, *, restore_root: Path | None = None) -> None:
    transaction = uuid.uuid4().hex
    staged: list[tuple[Path, Path, Path]] = []
    linked: list[tuple[Path, Path, Path]] = []
    committed: list[tuple[Path, Path, Path]] = []
    preserve_rollbacks: set[Path] = set()
    try:
        for item in manifest["files"]:
            target = safe_path(game_root, item["game_path"])
            source_hash = item["source_sha256"].lower()
            if restore_root is None:
                source = safe_path(MOD_ROOT, build_relative_path(item["build_path"]))
                expected = item["output_sha256"].lower()
            else:
                source = safe_path(restore_root, backup_relative_path(manifest, item))
                expected = source_hash
            temp = target.with_name(f".{target.name}.frog-stage-{transaction}")
            rollback = target.with_name(f".{target.name}.frog-rollback-{transaction}")
            staged.append((temp, target, rollback))
            shutil.copyfile(source, temp)
            if sha256(temp) != expected:
                raise ModError(f"Staged resource hash mismatch: {target}")

        for item, (_, target, _) in zip(manifest["files"], staged):
            safe_path(game_root, item["game_path"])
            require_regular_file(target, "game resource", reject_symlink=True)
            if sha256(target) not in (item["source_sha256"].lower(), item["output_sha256"].lower()):
                raise ModError(f"Game resource changed during preflight: {target}")

        # Keep a hard link to every old file before the first atomic replacement.
        for _, target, rollback in staged:
            linked.append((target, rollback, target))
            try:
                os.link(target, rollback)
            except OSError:
                shutil.copyfile(target, rollback)
        for temp, target, rollback in staged:
            os.replace(temp, target)
            committed.append((target, rollback, target))
    except Exception as exc:
        rollback_errors: list[str] = []
        for target, rollback, _ in reversed(committed):
            try:
                os.replace(rollback, target)
            except OSError as rollback_exc:
                preserve_rollbacks.add(rollback)
                rollback_errors.append(f"{target}: {rollback_exc}")
        if rollback_errors:
            raise ModError("Transaction failed and rollback was incomplete; preserve files "
                            "ending in .frog-rollback- for manual recovery: " + "; ".join(rollback_errors)) from exc
        if isinstance(exc, ModError):
            raise
        raise ModError(f"Transaction failed; all replaced files were rolled back: {exc}") from exc
    finally:
        for temp, _, _ in staged:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        for _, rollback, _ in linked:
            if rollback not in preserve_rollbacks:
                try:
                    rollback.unlink(missing_ok=True)
                except OSError:
                    pass


def restore_backup(game_root: Path) -> Path:
    versions_root = safe_path(MOD_ROOT, "backup/versions")
    if not versions_root.is_dir():
        raise ModError("No version-bound backup exists for this game directory")
    valid: list[tuple[float, Path, dict]] = []
    reasons: list[str] = []
    try:
        entries = list(versions_root.iterdir())
    except OSError as exc:
        raise ModError(f"Cannot inspect backup versions: {exc}") from exc
    for entry in entries:
        if ".pending-" in entry.name:
            continue
        try:
            relative = entry.relative_to(MOD_ROOT).as_posix()
            backup_root = safe_path(MOD_ROOT, relative)
            if not backup_root.is_dir():
                continue
            manifest_path = safe_path(MOD_ROOT, f"{relative}/manifest.json")
            saved = read_manifest(manifest_path)
            if not _same_game_path(saved.get("game_path"), game_root):
                continue
            _assert_backup(saved, backup_root, game_root)
            assert_targets(saved, game_root)
            valid.append((backup_root.stat().st_mtime, backup_root, saved))
        except (ModError, OSError, ValueError) as exc:
            reasons.append(str(exc))
    if not valid:
        suffix = " " + "; ".join(reasons) if reasons else ""
        raise ModError("No valid backup for this game directory and version was found." + suffix)
    valid.sort(key=lambda choice: choice[0], reverse=True)
    _, backup_root, saved = valid[0]
    _transaction(saved, game_root, restore_root=backup_root)
    return backup_root


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or restore the Silver Pines frog mod on SteamOS/Proton.")
    commands = parser.add_subparsers(dest="operation", required=True)
    for operation in ("install", "restore"):
        command = commands.add_parser(operation)
        command.add_argument("game_path", nargs="?", help="Game directory, or Carpenter.exe path")
        command.add_argument("--game-directory", dest="game_directory",
                             help="Game directory containing Carpenter.exe")
    args = parser.parse_args(argv)
    if args.game_path and args.game_directory:
        parser.error("pass a game path either positionally or with --game-directory, not both")
    args.game_directory = args.game_directory or args.game_path
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        game_root = find_game_directory(args.game_directory)
        assert_game_not_running()
        if args.operation == "install":
            manifest_path = safe_path(MOD_ROOT, "build/manifest.json")
            manifest = read_manifest(manifest_path)
            assert_game_version(manifest, game_root)
            assert_build(manifest)
            assert_targets(manifest, game_root)
            all_pristine = all(
                sha256(safe_path(game_root, item["game_path"])) == item["source_sha256"].lower()
                for item in manifest["files"]
            )
            backup_relative = f"backup/versions/{backup_key(manifest_path, manifest, game_root)}"
            existing_backup = safe_path(MOD_ROOT, backup_relative).exists()
            if not existing_backup and not all_pristine:
                raise ModError("Modded resources exist without a matching original backup. Verify game files in Steam first.")
            backup_root = create_backup(manifest_path, manifest, game_root)
            _transaction(manifest, game_root)
            print(f"Installed {len(manifest['files'])} resources to {game_root}")
            print(f"Original backup: {backup_root}")
        else:
            backup_root = restore_backup(game_root)
            print(f"Restored original resources from {backup_root}")
        return 0
    except ModError as exc:
        print(f"Operation cancelled: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
