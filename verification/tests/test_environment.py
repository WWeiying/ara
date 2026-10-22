import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ara_verify.dependencies import LockedTool
from ara_verify.dependency_patches import PatchError
from ara_verify.environment import (
    _dependency_check,
    _git_output,
    _tool_check,
    bender_lock_revision,
    config_values,
    has_errors,
)


class ConfigTests(unittest.TestCase):
    def test_config_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/default.mk").write_text(
                "nr_lanes ?= 4\nvlen ?= 1024\n", encoding="utf-8"
            )
            self.assertEqual(config_values(root, "default"), {"nr_lanes": 4, "vlen": 1024})

    def test_bender_lock_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "Bender.lock"
            lock.write_text(
                "packages:\n"
                "  cva6:\n"
                "    revision: 0123abcdef\n"
                "    source:\n"
                "      Git: https://example.com/cva6.git\n"
                "    dependencies: []\n"
                "  fpnew:\n"
                "    revision: fedcba3210\n"
                "    source:\n"
                "      Git: https://example.com/fpnew.git\n",
                encoding="utf-8",
            )
            self.assertEqual(bender_lock_revision(lock, "cva6"), "0123abcdef")
            self.assertIsNone(bender_lock_revision(lock, "missing"))

    def test_git_output_preserves_porcelain_status_prefix(self):
        with patch("ara_verify.environment.subprocess.run") as runner:
            runner.return_value = SimpleNamespace(returncode=0, stdout=" M first.sv\n M second.sv\n")
            self.assertEqual(_git_output(Path("/tmp/repo"), "status"), " M first.sv\n M second.sv")


class DependencyEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.revision = "a" * 40
        self.dependency = self.root / "hardware/deps/cva6"
        sources = self.dependency / "core/cache_subsystem/hpdcache/rtl/src"
        sources.mkdir(parents=True)
        for name in ("hpdcache_pkg.sv", "hpdcache.sv"):
            (sources / name).touch()
        (self.root / "Bender.lock").write_text(
            "packages:\n  cva6:\n"
            f"    revision: {self.revision}\n"
            "    source:\n      Git: https://example.com/cva6.git\n",
            encoding="utf-8",
        )
        self.git = self.start_patch("_git_output", return_value=self.revision)
        self.state = self.start_patch("patch_state", return_value="applied")
        self.submodules = self.start_patch("validate_submodules")
        self.start_patch("subprocess.run", side_effect=AssertionError("unexpected subprocess"))

    def start_patch(self, name, **kwargs):
        patcher = patch(f"ara_verify.environment.{name}", **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def check(self):
        return {item.name: item for item in _dependency_check(self.root, "cva6")}

    def test_approved_patch_uses_shared_state_and_nested_validation(self):
        checks = self.check()
        self.assertFalse(has_errors(checks.values()))
        self.assertIn("approved patch", checks["cva6 worktree"].detail)
        self.state.assert_called_once_with(self.root, "cva6", self.dependency, self.revision)
        self.submodules.assert_called_once_with(self.dependency, "cva6")

    def test_missing_required_patch_is_error_on_clean_base(self):
        self.state.return_value = "missing"
        checks = self.check()
        self.assertEqual(checks["cva6 revision"].level, "OK")
        self.assertEqual(checks["cva6 worktree"].level, "ERROR")
        self.assertIn("required patch", checks["cva6 worktree"].detail)

    def test_unpatched_package_accepts_clean_state(self):
        self.state.return_value = "clean"
        checks = self.check()
        self.assertEqual(checks["cva6 worktree"].level, "OK")
        self.assertEqual(checks["cva6 worktree"].detail, "compiled target sources: clean")

    def test_optional_unbuilt_submodule_dirt_does_not_override_target_approval(self):
        optional_status = " M FPGA/src/apb\n M riscv-dbg\n M common_verif\n M docs"
        self.git.side_effect = lambda path, *args: self.revision if args == ("rev-parse", "HEAD") else optional_status
        checks = self.check()
        self.assertFalse(has_errors(checks.values()))
        self.assertEqual(checks["cva6 worktree"].detail, "compiled target sources: approved patch applied")
        self.git.assert_called_once_with(self.dependency, "rev-parse", "HEAD")
        self.submodules.assert_called_once_with(self.dependency, "cva6")

    def test_other_dependencies_also_use_patch_registry(self):
        dependency = self.root / "hardware/deps/axi"
        dependency.mkdir()
        lock = self.root / "Bender.lock"
        lock.write_text(
            lock.read_text(encoding="utf-8") +
            f"  axi:\n    revision: {self.revision}\n"
            "    source:\n      Git: https://example.com/axi.git\n",
            encoding="utf-8",
        )
        self.state.return_value = "missing"
        checks = {item.name: item for item in _dependency_check(self.root, "axi")}
        self.assertEqual(checks["axi worktree"].level, "ERROR")
        self.state.assert_called_once_with(self.root, "axi", dependency, self.revision)

    def test_patch_failures_are_doctor_errors(self):
        for reason in ("unapproved local changes", "digest mismatch", "missing registry", "wrong revision"):
            with self.subTest(reason=reason):
                self.state.side_effect = PatchError(reason)
                check = self.check()["cva6 worktree"]
                self.assertEqual(check.level, "ERROR")
                self.assertEqual(check.detail, reason)

    def test_nested_pins_and_dirt_are_checked_even_when_files_exist(self):
        for reason in (
            "hpdcache wrong HEAD", "cvfpu wrong HEAD", "staged gitlink edit",
            "nested dirty worktree", "required submodule is not initialized",
        ):
            with self.subTest(reason=reason):
                self.submodules.side_effect = PatchError(reason)
                check = self.check()["cva6 submodules"]
                self.assertEqual(check.level, "ERROR")
                self.assertEqual(check.detail, reason)

    def test_wrong_parent_revision_is_reported(self):
        self.git.return_value = "b" * 40
        self.state.side_effect = PatchError("wrong revision")
        checks = self.check()
        self.assertEqual(checks["cva6 revision"].level, "ERROR")
        self.assertEqual(checks["cva6 worktree"].level, "ERROR")

    def test_missing_lock_revision_cannot_approve_patch(self):
        (self.root / "Bender.lock").unlink()
        checks = self.check()
        self.assertEqual(checks["cva6 revision"].level, "ERROR")
        self.assertEqual(checks["cva6 worktree"].level, "ERROR")
        self.state.assert_not_called()

    def test_malformed_lock_is_reported(self):
        (self.root / "Bender.lock").write_text("packages:\n  cva6:\n", encoding="utf-8")
        self.assertEqual(self.check()["cva6 revision"].level, "ERROR")
        self.state.assert_not_called()

    def test_missing_and_symlink_dependencies_are_rejected(self):
        for name in ("missing", "linked", "dangling"):
            with self.subTest(name=name):
                path = self.root / "hardware/deps" / name
                if name != "missing":
                    path.symlink_to(self.dependency if name == "linked" else self.root / "absent")
                self.assertTrue(has_errors(_dependency_check(self.root, name)))
        self.git.assert_not_called()
        self.state.assert_not_called()


class ToolEnvironmentTests(unittest.TestCase):
    def test_tools_require_exact_clean_revision_including_nested_dirt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = LockedTool("riscv-dv-rvv1", "a" * 40, "https://example.com/tool.git", "main", Path("tool"))
            source = root / tool.path / "src/isa/rv32v_instr.sv"
            source.parent.mkdir(parents=True)
            source.write_text("VSETIVLI VFREDUSUM_VS VCPOP_M", encoding="utf-8")
            for status in ("", " M src/isa/rv32v_instr.sv", " M nested", "?? untracked", None):
                with self.subTest(status=status), patch("ara_verify.environment._git_output") as git:
                    git.side_effect = [tool.revision, status]
                    checks = {item.name: item for item in _tool_check(root, tool)}
                    self.assertEqual(checks["tool:riscv-dv-rvv1 worktree"].level, "OK" if status == "" else "ERROR")
                    git.assert_any_call(root / tool.path, "status", "--porcelain=v1", "--ignore-submodules=none")
            with patch("ara_verify.environment._git_output", side_effect=["b" * 40, ""]):
                self.assertTrue(has_errors(_tool_check(root, tool)))
