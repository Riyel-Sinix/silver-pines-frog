"""Exercise the Windows installer against disposable fixtures, never a real game."""
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


HELPER = Path(__file__).resolve().parents[1] / "frogmod" / "manage_frog.ps1"
PYTHON_SPEC = importlib.util.spec_from_file_location("manage_frog_cross_installer", HELPER.with_suffix(".py"))
assert PYTHON_SPEC is not None and PYTHON_SPEC.loader is not None
python_installer = importlib.util.module_from_spec(PYTHON_SPEC)
PYTHON_SPEC.loader.exec_module(python_installer)
PREFIX = "Carpenter_Data/StreamingAssets/aa/StandaloneWindows64/"
MAIN = "team17_auto_base_characters_compressed_assets_player.bundle"
METADATA = "Carpenter_Data/il2cpp_data/Metadata/global-metadata.dat"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="奶蛙安装测试 ")
        self.root = Path(self.temporary.name)
        self.mod = self.root / "模组 包"
        self.game = self.root / "新版 游戏"
        self.mod.mkdir()
        self.game.mkdir()
        shutil.copyfile(HELPER, self.mod / HELPER.name)
        for name in ("install_frog.bat", "restore_original.bat"):
            shutil.copyfile(HELPER.parent / name, self.mod / name)
        (self.game / "Carpenter.exe").write_bytes(b"fixture executable")
        (self.game / "GameAssembly.dll").write_bytes(b"fixture code version 1")
        self.write_game(METADATA, b"fixture metadata version 1")
        self.files = []
        self.originals = {}
        for index, (game_path, build_path) in enumerate([
            (PREFIX + MAIN, MAIN),
            (PREFIX + "fixture.bundle", "patches/fixture.bundle"),
            ("Carpenter_Data/globalgamemanagers", "globalgamemanagers"),
        ]):
            original = f"original resource {index}".encode()
            output = f"modified resource {index}".encode()
            self.originals[game_path] = original
            self.write_game(game_path, original)
            path = self.mod / "build" / build_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(output)
            self.files.append({"game_path": game_path, "build_path": build_path,
                               "source_sha256": digest(original), "output_sha256": digest(output)})
        (self.mod / "build/patches/bundles.txt").write_text("fixture.bundle\n", encoding="utf-8")
        self.manifest = {
            "schema_version": 1,
            "game": {"unity_version": "fixture", "steam_build_id": "fixture",
                     "gameassembly_sha256": digest((self.game / "GameAssembly.dll").read_bytes()),
                     "metadata_sha256": digest((self.game / METADATA).read_bytes())},
            "files": self.files,
        }
        self.save_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def write_game(self, name, data):
        path = self.game / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def save_manifest(self):
        (self.mod / "build/manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_installer(self, operation="Install", success=True):
        result = subprocess.run([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(self.mod / HELPER.name), "-Operation", operation,
            "-GameDirectory", str(self.game),
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0 if success else 1,
                         result.stdout.decode("utf-8", errors="replace"))
        return result

    def run_python_installer(self, operation="install"):
        with mock.patch.object(python_installer, "MOD_ROOT", self.mod), \
                mock.patch.object(python_installer, "assert_game_not_running"):
            result = python_installer.main([operation, "--game-directory", str(self.game)])
        self.assertEqual(result, 0)

    def assert_original(self):
        for path, original in self.originals.items():
            self.assertEqual((self.game / path).read_bytes(), original)

    def backup_root(self):
        return next((self.mod / "backup/versions").iterdir())

    def saved_manifest(self):
        return json.loads((self.backup_root() / "manifest.json").read_text(encoding="utf-8-sig"))

    def backup_payload(self, file):
        if self.saved_manifest().get("backup_layout") == "sha256-v1":
            return self.backup_root() / "files" / (file["source_sha256"] + ".bin")
        return self.backup_root() / file["game_path"]

    def test_install_reinstall_restore_without_build(self):
        self.run_installer()
        for file in self.files:
            self.assertEqual(digest((self.game / file["game_path"]).read_bytes()), file["output_sha256"])
        self.run_installer()
        shutil.rmtree(self.mod / "build")
        self.run_installer("Restore")
        self.assert_original()
        self.run_installer("Restore")
        self.assert_original()

    def test_missing_build_manifest(self):
        (self.mod / "build/manifest.json").unlink()
        self.run_installer(success=False)
        self.assert_original()
        self.assertFalse((self.mod / "backup").exists())

    def test_bat_launchers_from_chinese_package_path(self):
        for name in ("install_frog.bat", "restore_original.bat"):
            result = subprocess.run(
                f'"{self.mod / name}" "{self.game}"', shell=True,
                input=b"\n", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", errors="replace"))
        self.assert_original()

    def test_optional_audio_and_empty_patch_list(self):
        self.manifest["files"] = self.files[:1]
        self.save_manifest()
        (self.mod / "build/patches/bundles.txt").write_text("", encoding="utf-8")
        self.run_installer()
        self.run_installer("Restore")
        self.assert_original()

    def test_wrong_game_version(self):
        (self.game / "GameAssembly.dll").write_bytes(b"updated code")
        self.run_installer(success=False)
        self.assert_original()

    def test_corrupt_build(self):
        (self.mod / "build" / MAIN).write_bytes(b"incomplete download")
        self.run_installer(success=False)
        self.assert_original()

    def test_patch_list_mismatch(self):
        (self.mod / "build/patches/bundles.txt").write_text("missing.bundle\n", encoding="utf-8")
        self.run_installer(success=False)
        self.assert_original()

    def test_legacy_backup_not_restored(self):
        legacy = self.mod / "backup" / MAIN
        legacy.parent.mkdir()
        legacy.write_bytes(b"old game resource")
        self.run_installer("Restore", success=False)
        self.assert_original()
        self.run_installer()
        self.assertEqual(legacy.read_bytes(), b"old game resource")

    def test_corrupt_backup_refuses_all_files(self):
        self.run_installer()
        before = {file["game_path"]: (self.game / file["game_path"]).read_bytes() for file in self.files}
        self.backup_payload(self.files[-1]).write_bytes(b"bad backup")
        self.run_installer("Restore", success=False)
        for name, value in before.items():
            self.assertEqual((self.game / name).read_bytes(), value)

    def test_updated_game_cannot_restore_old_resources(self):
        self.run_installer()
        (self.game / METADATA).write_bytes(b"updated metadata")
        self.run_installer("Restore", success=False)
        for file in self.files:
            self.assertEqual(digest((self.game / file["game_path"]).read_bytes()), file["output_sha256"])

    def test_same_size_unknown_resource_refuses_restore(self):
        self.run_installer()
        path = self.game / self.files[-1]["game_path"]
        path.write_bytes(b"x" * path.stat().st_size)
        self.run_installer("Restore", success=False)
        self.assertEqual(digest((self.game / self.files[0]["game_path"]).read_bytes()), self.files[0]["output_sha256"])

    def test_other_install_directory_cannot_use_backup(self):
        self.run_installer()
        destination = self.root / "另一份 游戏"
        shutil.copytree(self.game, destination)
        self.game = destination
        self.run_installer("Restore", success=False)

    def test_modified_game_without_backup_cannot_seed_backup(self):
        for file in self.files:
            shutil.copyfile(self.mod / "build" / file["build_path"], self.game / file["game_path"])
        self.run_installer(success=False)
        self.assertFalse((self.mod / "backup").exists())

    def test_locked_second_file_rolls_back_first(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                      ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(self.game / self.files[1]["game_path"]),
                                    0x80000000, 0x1 | 0x2, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            self.run_installer(success=False)
            self.assert_original()
            self.assertFalse(list(self.game.rglob("*.frog-*")))
        finally:
            kernel.CloseHandle(handle)

    def test_longest_real_bundle_uses_short_backup_and_transaction_paths(self):
        name = ("team17_auto_patch_general_compressed_assets_"
                "playerreloadboltactionarm_lowresvariant_"
                "1d69ec7918e115677845ceae4e47ef8b.bundle")
        original_path = self.files[1]["game_path"]
        original = self.originals.pop(original_path)
        (self.game / original_path).unlink()
        self.files[1]["game_path"] = PREFIX + name
        self.files[1]["build_path"] = "patches/" + name
        self.originals[PREFIX + name] = original
        self.write_game(PREFIX + name, original)
        (self.mod / "build/patches/fixture.bundle").rename(self.mod / "build/patches" / name)
        (self.mod / "build/patches/bundles.txt").write_text(name + "\n", encoding="utf-8")
        self.save_manifest()

        # Assert every hashed path fits old PowerShell's limit even on hosts
        # whose registry/.NET configuration enables long paths.
        helper = self.mod / HELPER.name
        source = helper.read_text(encoding="utf-8-sig")
        source = source.replace("function Get-Hash([string]$Path) {",
                                "function Get-Hash([string]$Path) {\n"
                                "    if ($Path.Length -ge 260) { throw 'MAX_PATH regression' }")
        helper.write_text(source, encoding="utf-8-sig")

        self.run_installer()
        self.assertEqual(self.saved_manifest()["backup_layout"], "sha256-v1")
        for file in self.files:
            self.assertLess(len(str(self.backup_payload(file))), 260)
        self.run_installer()
        shutil.rmtree(self.mod / "build")
        self.run_installer("Restore")
        self.assert_original()
        self.assertFalse(list(self.game.rglob("*.frog-*")))
        self.assertFalse(list((self.mod / "backup").glob(".pending-*")))

    def test_legacy_version_backup_can_reinstall_and_restore(self):
        self.run_installer()
        saved = self.saved_manifest()
        for file in saved["files"]:
            compact = self.backup_payload(file)
            legacy = self.backup_root() / file["game_path"]
            legacy.parent.mkdir(parents=True, exist_ok=True)
            compact.rename(legacy)
        saved.pop("backup_layout")
        (self.backup_root() / "manifest.json").write_text(json.dumps(saved), encoding="utf-8")
        self.run_installer()
        shutil.rmtree(self.mod / "build")
        self.run_installer("Restore")
        self.assert_original()

    def test_unknown_backup_layout_refuses_restore(self):
        self.run_installer()
        saved = self.saved_manifest()
        saved["backup_layout"] = "unknown-layout"
        (self.backup_root() / "manifest.json").write_text(json.dumps(saved), encoding="utf-8")
        self.run_installer("Restore", success=False)
        for file in self.files:
            self.assertEqual(digest((self.game / file["game_path"]).read_bytes()), file["output_sha256"])

    def test_powershell_compact_backup_can_restore_with_python(self):
        self.run_installer()
        self.assertEqual(self.saved_manifest()["backup_layout"], "sha256-v1")
        shutil.rmtree(self.mod / "build")
        self.run_python_installer("restore")
        self.assert_original()

    def test_python_compact_backup_can_reinstall_and_restore_with_powershell(self):
        self.run_python_installer()
        self.assertEqual(self.saved_manifest()["backup_layout"], "sha256-v1")
        backup_root = self.backup_root()
        for file in self.files:
            self.assertEqual(digest((self.game / file["game_path"]).read_bytes()), file["output_sha256"])
        self.run_installer()
        self.assertEqual(list((self.mod / "backup/versions").iterdir()), [backup_root])
        shutil.rmtree(self.mod / "build")
        self.run_installer("Restore")
        self.assert_original()


if __name__ == "__main__":
    unittest.main()
