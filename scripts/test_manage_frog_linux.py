"""Cross-platform tests for the SteamOS/Proton installer using disposable games."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


HELPER_PATH = Path(__file__).resolve().parents[1] / "frogmod" / "manage_frog.py"
SPEC = importlib.util.spec_from_file_location("manage_frog_linux", HELPER_PATH)
assert SPEC is not None and SPEC.loader is not None
manage_frog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_frog)

PREFIX = "Carpenter_Data/StreamingAssets/aa/StandaloneWindows64/"
MAIN = "team17_auto_base_characters_compressed_assets_player.bundle"
METADATA = "Carpenter_Data/il2cpp_data/Metadata/global-metadata.dat"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ProtonInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="奶蛙 Steam Deck 测试 ")
        self.root = Path(self.temporary.name)
        self.mod = self.root / "奶蛙 发行包"
        self.game = self.root / "新版 中文游戏"
        self.mod.mkdir()
        self.game.mkdir()
        self.build = self.mod / "build"
        (self.game / "Carpenter_Data").mkdir()
        (self.game / "Carpenter.exe").write_bytes(b"Windows game executable")
        (self.game / "GameAssembly.dll").write_bytes(b"fixture code version 1")
        self.write_game(METADATA, b"fixture metadata version 1")
        self.files: list[dict[str, str]] = []
        self.originals: dict[str, bytes] = {}
        specifications = [
            (PREFIX + MAIN, "patches/" + MAIN),
            (PREFIX + "fixture.bundle", "patches/fixture.bundle"),
            ("Carpenter_Data/globalgamemanagers", "globalgamemanagers"),
        ]
        for index, (game_path, build_path) in enumerate(specifications):
            original = f"原版资源 {index}".encode("utf-8")
            output = f"奶蛙资源 {index}".encode("utf-8")
            self.originals[game_path] = original
            self.write_game(game_path, original)
            built = self.build / build_path
            built.parent.mkdir(parents=True, exist_ok=True)
            built.write_bytes(output)
            self.files.append({
                "game_path": game_path,
                "build_path": build_path,
                "source_sha256": digest(original),
                "output_sha256": digest(output),
            })
        patch_list = self.build / "patches/bundles.txt"
        patch_list.parent.mkdir(parents=True, exist_ok=True)
        patch_list.write_text("".join(item["build_path"][8:] + "\n" for item in self.files
                                       if item["build_path"].startswith("patches/")), encoding="utf-8")
        self.manifest = {
            "schema_version": 1,
            "game": {
                "unity_version": "fixture",
                "steam_build_id": "fixture",
                "gameassembly_sha256": digest((self.game / "GameAssembly.dll").read_bytes()),
                "metadata_sha256": digest((self.game / METADATA).read_bytes()),
            },
            "files": self.files,
        }
        self.save_manifest()
        self.old_mod_root = manage_frog.MOD_ROOT
        manage_frog.MOD_ROOT = self.mod

    def tearDown(self) -> None:
        manage_frog.MOD_ROOT = self.old_mod_root
        self.temporary.cleanup()

    def write_game(self, relative: str, data: bytes) -> None:
        path = self.game.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def save_manifest(self) -> None:
        self.build.mkdir(parents=True, exist_ok=True)
        (self.build / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_operation(self, operation: str = "install", success: bool = True) -> int:
        with mock.patch.object(manage_frog, "assert_game_not_running"):
            result = manage_frog.main([operation, "--game-directory", str(self.game)])
        self.assertEqual(result, 0 if success else 1)
        return result

    def assert_original(self) -> None:
        for relative, content in self.originals.items():
            self.assertEqual(self.game.joinpath(*relative.split("/")).read_bytes(), content)

    def assert_installed(self) -> None:
        for item in self.files:
            target = self.game.joinpath(*item["game_path"].split("/"))
            self.assertEqual(digest(target.read_bytes()), item["output_sha256"])

    def test_install_reinstall_restore_after_build_is_removed(self) -> None:
        self.run_operation()
        self.assert_installed()
        backup_root = next((self.mod / "backup/versions").iterdir())
        saved = manage_frog.read_manifest(backup_root / "manifest.json")
        self.assertEqual(saved["backup_layout"], "sha256-v1")
        self.assertFalse((backup_root / "Carpenter_Data").exists())
        for item in self.files:
            payload = backup_root / "files" / (item["source_sha256"] + ".bin")
            self.assertEqual(payload.read_bytes(), self.originals[item["game_path"]])
        self.run_operation()
        self.assert_installed()
        shutil.rmtree(self.build)
        self.run_operation("restore")
        self.assert_original()

    def test_legacy_mirrored_backup_supports_reinstall_and_restore(self) -> None:
        manifest_path = self.build / "manifest.json"
        key = manage_frog.backup_key(manifest_path, self.manifest, self.game.resolve())
        backup_root = self.mod / "backup/versions" / key
        backup_root.mkdir(parents=True)
        saved = dict(self.manifest)
        saved["game_path"] = str(self.game.resolve())
        (backup_root / "manifest.json").write_text(json.dumps(saved), encoding="utf-8")
        for relative, content in self.originals.items():
            destination = backup_root.joinpath(*relative.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

        self.run_operation()
        self.assert_installed()
        self.run_operation()
        self.assert_installed()
        self.assertNotIn("backup_layout", manage_frog.read_manifest(backup_root / "manifest.json"))
        shutil.rmtree(self.build)
        self.run_operation("restore")
        self.assert_original()

    def test_unknown_or_null_backup_layout_is_rejected(self) -> None:
        for layout in (None, "future-layout", "", 1):
            with self.subTest(layout=layout):
                self.manifest["backup_layout"] = layout
                self.save_manifest()
                self.run_operation(success=False)
                self.assert_original()
                self.assertFalse((self.mod / "backup").exists())

    def test_wrong_game_version_is_rejected_before_backup_or_writes(self) -> None:
        (self.game / "GameAssembly.dll").write_bytes(b"different build")
        self.run_operation(success=False)
        self.assert_original()
        self.assertFalse((self.mod / "backup").exists())

    def test_corrupt_output_hash_is_rejected_before_writes(self) -> None:
        built = self.build / self.files[1]["build_path"]
        built.write_bytes(b"truncated bundle")
        self.run_operation(success=False)
        self.assert_original()
        self.assertFalse((self.mod / "backup").exists())

    def test_corrupt_manifest_and_patch_list_are_rejected(self) -> None:
        self.manifest["schema_version"] = 99
        self.save_manifest()
        self.run_operation(success=False)
        self.assert_original()
        self.manifest["schema_version"] = 1
        self.save_manifest()
        (self.build / "patches/bundles.txt").write_text("not-in-manifest.bundle\n", encoding="utf-8")
        self.run_operation(success=False)
        self.assert_original()

    def test_unbound_legacy_backup_is_not_restored(self) -> None:
        legacy = self.mod / "backup" / MAIN
        legacy.parent.mkdir()
        legacy.write_bytes(b"legacy file without game identity")
        self.run_operation("restore", success=False)
        self.assert_original()
        self.run_operation()
        self.assertEqual(legacy.read_bytes(), b"legacy file without game identity")

    def test_backup_is_bound_to_absolute_game_directory(self) -> None:
        self.run_operation()
        other_game = self.root / "另一份游戏"
        shutil.copytree(self.game, other_game)
        original_game = self.game
        try:
            self.game = other_game
            self.run_operation("restore", success=False)
        finally:
            self.game = original_game

    def test_auto_discovery_finds_secondary_steam_library_with_spaces(self) -> None:
        home = self.root / "deck home"
        steam_root = home / ".local/share/Steam"
        steamapps = steam_root / "steamapps"
        steamapps.mkdir(parents=True)
        library = self.root / "SD card Steam Library"
        game = library / "steamapps/common/Silver Pines"
        game.parent.mkdir(parents=True)
        shutil.copytree(self.game, game)
        escaped_library = str(library).replace("\\", "\\\\")
        (steamapps / "libraryfolders.vdf").write_text(
            f'"libraryfolders" {{ "1" {{ "path" "{escaped_library}" }} }}',
            encoding="utf-8",
        )

        with mock.patch.object(manage_frog.Path, "home", return_value=home):
            found = manage_frog.find_game_directory(None)

        self.assertEqual(found, game.resolve())

    def test_corrupt_backup_refuses_restore_before_writing(self) -> None:
        self.run_operation()
        backup_root = next((self.mod / "backup/versions").iterdir())
        saved = manage_frog.read_manifest(backup_root / "manifest.json")
        damaged = backup_root / manage_frog.backup_relative_path(saved, self.files[-1])
        damaged.write_bytes(b"corrupt original")
        self.run_operation("restore", success=False)
        self.assert_installed()

    def test_replace_failure_rolls_back_every_target(self) -> None:
        original_replace = manage_frog.os.replace
        stage_replace_count = 0
        injected = False

        def flaky_replace(source: str | Path, target: str | Path) -> None:
            nonlocal stage_replace_count, injected
            if ".frog-stage-" in Path(source).name:
                stage_replace_count += 1
                if stage_replace_count == 2 and not injected:
                    injected = True
                    raise OSError("injected atomic replacement failure")
            original_replace(source, target)

        with mock.patch.object(manage_frog, "assert_game_not_running"), \
                mock.patch.object(manage_frog.os, "replace", side_effect=flaky_replace):
            result = manage_frog.main(["install", "--game-directory", str(self.game)])
        self.assertEqual(result, 1)
        self.assertTrue(injected)
        self.assert_original()
        self.assertFalse(list(self.game.rglob("*.frog-stage-*")))
        self.assertFalse(list(self.game.rglob("*.frog-rollback-*")))

    def test_partial_stage_copy_failure_removes_temporary_files(self) -> None:
        original_copyfile = manage_frog.shutil.copyfile
        stage_copy_count = 0
        injected = False

        def flaky_copyfile(source: str | Path, target: str | Path) -> str:
            nonlocal stage_copy_count, injected
            result = original_copyfile(source, target)
            if ".frog-stage-" in Path(target).name:
                stage_copy_count += 1
                if stage_copy_count == 2 and not injected:
                    injected = True
                    raise OSError("injected staging copy failure")
            return result

        with mock.patch.object(manage_frog, "assert_game_not_running"), \
                mock.patch.object(manage_frog.shutil, "copyfile", side_effect=flaky_copyfile):
            result = manage_frog.main(["install", "--game-directory", str(self.game)])

        self.assertEqual(result, 1)
        self.assertTrue(injected)
        self.assert_original()
        self.assertFalse(list(self.game.rglob("*.frog-stage-*")))
        self.assertFalse(list(self.game.rglob("*.frog-rollback-*")))

    def test_partial_rollback_copy_failure_removes_temporary_files(self) -> None:
        original_copyfile = manage_frog.shutil.copyfile
        injected = False

        def unsupported_link(source: str | Path, target: str | Path) -> None:
            raise OSError("injected unsupported hard links")

        def flaky_copyfile(source: str | Path, target: str | Path) -> str:
            nonlocal injected
            result = original_copyfile(source, target)
            if ".frog-rollback-" in Path(target).name and not injected:
                injected = True
                raise OSError("injected rollback copy failure")
            return result

        with mock.patch.object(manage_frog, "assert_game_not_running"), \
                mock.patch.object(manage_frog.os, "link", side_effect=unsupported_link), \
                mock.patch.object(manage_frog.shutil, "copyfile", side_effect=flaky_copyfile):
            result = manage_frog.main(["install", "--game-directory", str(self.game)])

        self.assertEqual(result, 1)
        self.assertTrue(injected)
        self.assert_original()
        self.assertFalse(list(self.game.rglob("*.frog-stage-*")))
        self.assertFalse(list(self.game.rglob("*.frog-rollback-*")))

    def test_symlink_escape_is_rejected(self) -> None:
        outside = self.root / "outside.bundle"
        outside.write_bytes(b"outside target")
        victim = self.build / self.files[1]["build_path"]
        victim.unlink()
        try:
            victim.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation is unavailable: {exc}")
        with self.assertRaises(manage_frog.ModError):
            manage_frog.assert_build(self.manifest)
        self.assertEqual(outside.read_bytes(), b"outside target")

    def test_game_resource_symlink_escape_is_rejected(self) -> None:
        outside = self.root / "outside.bundle"
        outside.write_bytes(self.originals[self.files[1]["game_path"]])
        target = self.game.joinpath(*self.files[1]["game_path"].split("/"))
        target.unlink()
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation is unavailable: {exc}")
        with self.assertRaises(manage_frog.ModError):
            manage_frog.assert_targets(self.manifest, self.game)


if __name__ == "__main__":
    unittest.main()
