import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from ara_verify.dependencies import (
    DependencyError,
    LockedTool,
    _sync_locked_tool,
    locked_dependencies,
    locked_tools,
    sync_dependencies,
)
from ara_verify.dependency_patches import PatchError


class DependencyLockTests(unittest.TestCase):
    def test_locked_git_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "Bender.lock"
            lock.write_text(
                "packages:\n"
                "  cva6:\n"
                "    revision: 0123abcdef\n"
                "    source:\n"
                "      Git: git@example.com:cva6.git\n"
                "    dependencies: []\n",
                encoding="utf-8",
            )
            self.assertEqual(
                locked_dependencies(lock)[0],
                locked_dependencies(lock)[0].__class__(
                    "cva6", "0123abcdef", "git@example.com:cva6.git"
                ),
            )

    def test_rejects_path_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "Bender.lock"
            lock.write_text(
                "packages:\n"
                "  cva6:\n"
                "    revision: null\n"
                "    source:\n"
                "      Path: hardware/deps/cva6\n",
                encoding="utf-8",
            )
            with self.assertRaises(DependencyError):
                locked_dependencies(lock)

    def test_locked_verification_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "toolchain.lock.json"
            lock.write_text(
                '{"schema_version":1,"tools":{"riscv-dv-rvv1":{'
                '"url":"https://example.com/riscv-dv.git",'
                '"fetch_ref":"refs/pull/1/head",'
                '"revision":"0123456789abcdef0123456789abcdef01234567",'
                '"path":"verification/tools/riscv-dv-rvv1"}}}',
                encoding="utf-8",
            )
            tool = locked_tools(lock)[0]
            self.assertEqual(tool.name, "riscv-dv-rvv1")
            self.assertEqual(tool.path, Path("verification/tools/riscv-dv-rvv1"))

    def test_rejects_tool_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "toolchain.lock.json"
            lock.write_text(
                '{"schema_version":1,"tools":{"bad":{'
                '"url":"https://example.com/tool.git","fetch_ref":"main",'
                '"revision":"0123456789abcdef0123456789abcdef01234567",'
                '"path":"../outside"}}}',
                encoding="utf-8",
            )
            with self.assertRaises(DependencyError):
                locked_tools(lock)


class DependencySyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.revision = "a" * 40
        self.actual = self.revision
        self.status = ""
        self.dependency = self.root / "hardware/deps/cva6"
        (self.dependency / ".git").mkdir(parents=True)
        (self.root / "Bender.lock").write_text(
            "packages:\n  cva6:\n"
            f"    revision: {self.revision}\n"
            "    source:\n      Git: https://example.com/cva6.git\n",
            encoding="utf-8",
        )
        self.registry = self.start_patch("load_registry", return_value={})
        self.tools = self.start_patch("locked_tools", return_value=[])
        self.git = self.start_patch("_git_output", side_effect=self.git_output)
        self.run = self.start_patch("_run", side_effect=self.run_command)
        self.state = self.start_patch("patch_state", return_value="applied")
        self.apply = self.start_patch("apply_patch_bundle", return_value="applied")
        self.ensure = self.start_patch("ensure_submodules")
        self.validate = self.start_patch("validate_submodules")
        self.start_patch("subprocess.run", side_effect=AssertionError("unexpected subprocess"))
        self.events = Mock()
        for name in ("state", "ensure", "apply", "run"):
            self.events.attach_mock(getattr(self, name), name)

    def start_patch(self, name, **kwargs):
        patcher = patch(f"ara_verify.dependencies.{name}", **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def git_output(self, path, *args):
        if args == ("rev-parse", "--is-inside-work-tree"):
            return "true"
        if args == ("rev-parse", "HEAD"):
            return self.actual
        if args == ("status", "--porcelain=v1", "--ignore-submodules=none"):
            return self.status
        self.fail(f"unexpected Git arguments: {args}")

    def run_command(self, command, cwd=None):
        if command[1] == "clone":
            (Path(command[-1]) / ".git").mkdir(parents=True)
        elif command[1] == "checkout":
            self.actual = command[-1]

    def test_approved_dirty_baseline_is_unchanged_without_checkout(self):
        self.status = "M  approved.sv\n M also-approved.sv"
        self.assertEqual(sync_dependencies(self.root), [("cva6", "unchanged")])
        args = (self.root, "cva6", self.dependency, self.revision)
        self.assertEqual(self.events.mock_calls, [
            call.state(*args), call.ensure(self.dependency, "cva6"), call.apply(*args),
        ])
        self.registry.assert_called_once_with(self.root)
        self.run.assert_not_called()

    def test_clean_base_installs_required_patch_and_initializes_submodules(self):
        self.state.return_value = "missing"
        self.assertEqual(sync_dependencies(self.root), [("cva6", "applied required patch")])
        self.ensure.assert_called_once_with(self.dependency, "cva6")
        self.apply.assert_called_once_with(self.root, "cva6", self.dependency, self.revision)
        self.run.assert_not_called()

    def test_optional_unbuilt_submodules_are_not_reset_or_rejected(self):
        self.status = " M FPGA/src/apb\n M FPGA/src/axi\n M riscv-dbg\n M common_verif\n M docs"
        self.assertEqual(sync_dependencies(self.root), [("cva6", "unchanged")])
        self.assertEqual(self.git.call_args_list, [
            call(self.dependency, "rev-parse", "--is-inside-work-tree"),
            call(self.dependency, "rev-parse", "HEAD"),
        ])
        self.ensure.assert_called_once_with(self.dependency, "cva6")
        self.run.assert_not_called()

    def test_clean_unpatched_dependency_is_unchanged(self):
        self.state.return_value = "clean"
        self.apply.return_value = "clean"
        self.assertEqual(sync_dependencies(self.root), [("cva6", "unchanged")])
        self.ensure.assert_called_once_with(self.dependency, "cva6")
        self.run.assert_not_called()

    def test_unknown_dirty_baseline_never_changes_any_checkout(self):
        self.state.side_effect = PatchError("unapproved local changes")
        with self.assertRaisesRegex(DependencyError, "unapproved local changes") as caught:
            sync_dependencies(self.root)
        self.assertIsInstance(caught.exception.__cause__, PatchError)
        self.ensure.assert_not_called()
        self.apply.assert_not_called()
        self.run.assert_not_called()

    def test_nested_preflight_failure_never_applies_patch(self):
        for reason in ("wrong nested pin", "nested dirty worktree", "staged gitlink edit"):
            with self.subTest(reason=reason):
                self.ensure.side_effect = PatchError(reason)
                with self.assertRaisesRegex(DependencyError, reason):
                    sync_dependencies(self.root)
                self.apply.assert_not_called()
                self.run.assert_not_called()

    def test_patch_application_failure_is_dependency_error(self):
        self.apply.side_effect = PatchError("cannot apply approved patch")
        with self.assertRaisesRegex(DependencyError, "cannot apply approved patch"):
            sync_dependencies(self.root)
        self.run.assert_not_called()

    def test_missing_or_tampered_registry_fails_before_git(self):
        for reason in ("missing registry", "digest mismatch"):
            with self.subTest(reason=reason):
                self.registry.side_effect = PatchError(reason)
                with self.assertRaisesRegex(DependencyError, reason):
                    sync_dependencies(self.root)
                self.git.assert_not_called()
                self.run.assert_not_called()
                self.ensure.assert_not_called()
                self.apply.assert_not_called()

    def test_revision_change_refuses_parent_and_nested_dirt(self):
        self.actual = "b" * 40
        for status in (" M local.sv", "M  staged.sv", "?? untracked", " M core/cvfpu", "M  core/cvfpu"):
            for dry_run in (False, True):
                with self.subTest(status=status, dry_run=dry_run):
                    self.status = status
                    with self.assertRaisesRegex(DependencyError, "dirty dependency"):
                        sync_dependencies(self.root, dry_run=dry_run)
                    self.run.assert_not_called()
                    self.state.assert_not_called()
                    self.ensure.assert_not_called()
                    self.apply.assert_not_called()

    def test_patch_registry_revision_mismatch_fails_before_git(self):
        self.registry.return_value = {"cva6": {"revision": "b" * 40}}
        with self.assertRaisesRegex(DependencyError, "patch base does not match Bender.lock"):
            sync_dependencies(self.root)
        self.git.assert_not_called()
        self.run.assert_not_called()
        self.ensure.assert_not_called()
        self.apply.assert_not_called()

    def test_clean_revision_change_checks_out_before_nested_and_patch_setup(self):
        self.actual = "b" * 40
        self.assertEqual(sync_dependencies(self.root), [("cva6", f"checked out {self.revision}")])
        self.assertEqual(self.events.mock_calls, [
            call.run(["git", "fetch", "--depth=1", "https://example.com/cva6.git", self.revision], cwd=self.dependency),
            call.run(["git", "checkout", "--detach", self.revision], cwd=self.dependency),
            call.ensure(self.dependency, "cva6"),
            call.apply(self.root, "cva6", self.dependency, self.revision),
        ])

    def test_missing_dependency_is_cloned_then_patched(self):
        (self.dependency / ".git").rmdir()
        self.dependency.rmdir()
        sync_dependencies(self.root)
        self.assertEqual(self.run.call_args_list[0], call([
            "git", "clone", "--no-checkout", "https://example.com/cva6.git", str(self.dependency),
        ]))
        self.ensure.assert_called_once_with(self.dependency, "cva6")
        self.apply.assert_called_once_with(self.root, "cva6", self.dependency, self.revision)

    def test_checkout_wrong_revision_does_not_initialize_or_patch(self):
        self.actual = "b" * 40
        self.run.side_effect = None
        with self.assertRaisesRegex(DependencyError, f"expected {self.revision}"):
            sync_dependencies(self.root)
        self.ensure.assert_not_called()
        self.apply.assert_not_called()

    def test_existing_non_git_path_is_not_replaced(self):
        (self.dependency / ".git").rmdir()
        with self.assertRaisesRegex(DependencyError, "non-Git dependency"):
            sync_dependencies(self.root)
        self.run.assert_not_called()
        self.git.assert_not_called()

    def test_symlink_and_dangling_symlink_are_not_followed(self):
        (self.dependency / ".git").rmdir()
        self.dependency.rmdir()
        for target in (self.root, self.root / "absent"):
            with self.subTest(target=target):
                self.dependency.symlink_to(target)
                with self.assertRaisesRegex(DependencyError, "symlink dependency"):
                    sync_dependencies(self.root)
                self.dependency.unlink()
                self.git.assert_not_called()
                self.run.assert_not_called()
                self.state.assert_not_called()

    def test_unreadable_head_and_status_are_not_treated_as_missing_or_clean(self):
        self.actual = None
        with self.assertRaisesRegex(DependencyError, "cannot read Git revision"):
            sync_dependencies(self.root)
        self.actual = "b" * 40
        self.status = None
        with self.assertRaisesRegex(DependencyError, "cannot read Git status"):
            sync_dependencies(self.root)
        self.run.assert_not_called()

    def test_dry_run_reports_missing_patch_without_mutating(self):
        self.state.return_value = "missing"
        self.assertEqual(sync_dependencies(self.root, dry_run=True), [("cva6", "apply required patch")])
        self.validate.assert_called_once_with(self.dependency, "cva6")
        self.ensure.assert_not_called()
        self.apply.assert_not_called()
        self.run.assert_not_called()

    def test_dry_run_validates_approved_patch_and_nested_checkouts(self):
        self.assertEqual(sync_dependencies(self.root, dry_run=True), [("cva6", "unchanged")])
        self.validate.assert_called_once_with(self.dependency, "cva6")
        self.validate.side_effect = PatchError("nested checkout is invalid")
        with self.assertRaisesRegex(DependencyError, "nested checkout is invalid"):
            sync_dependencies(self.root, dry_run=True)
        self.ensure.assert_not_called()
        self.apply.assert_not_called()
        self.run.assert_not_called()

    def test_dry_run_missing_dependency_does_not_create_it(self):
        (self.dependency / ".git").rmdir()
        self.dependency.rmdir()
        self.assertEqual(sync_dependencies(self.root, dry_run=True), [("cva6", f"checkout {self.revision}")])
        self.assertFalse(self.dependency.exists())
        self.ensure.assert_not_called()
        self.apply.assert_not_called()
        self.run.assert_not_called()


class ToolSyncTests(unittest.TestCase):
    def test_tool_revision_update_rechecks_nested_cleanliness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = LockedTool("riscv-dv-rvv1", "a" * 40, "https://example.com/tool.git", "main", Path("tool"))
            path = root / tool.path
            (path / ".git").mkdir(parents=True)
            for final_status in ("", " M nested"):
                with self.subTest(final_status=final_status):
                    with patch("ara_verify.dependencies._git_output", side_effect=[
                        "true", "b" * 40, "", "true", tool.revision, final_status,
                    ]) as git, patch("ara_verify.dependencies._run") as run:
                        if final_status:
                            with self.assertRaisesRegex(DependencyError, "dirty dependency"):
                                _sync_locked_tool(root, tool, False)
                        else:
                            self.assertEqual(
                                _sync_locked_tool(root, tool, False),
                                ("tool:riscv-dv-rvv1", f"checked out {tool.revision}"),
                            )
                        self.assertEqual(run.call_args_list, [
                            call(["git", "fetch", "--depth=1", "origin", tool.fetch_ref], cwd=path),
                            call(["git", "checkout", "--detach", tool.revision], cwd=path),
                        ])
                        status_call = call(path, "status", "--porcelain=v1", "--ignore-submodules=none")
                        self.assertEqual(git.call_args_list.count(status_call), 2)

    def test_tools_reject_dirty_parent_or_submodule_at_any_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = LockedTool("riscv-dv-rvv1", "a" * 40, "https://example.com/tool.git", "main", Path("tool"))
            path = root / tool.path
            (path / ".git").mkdir(parents=True)
            for revision in (tool.revision, "b" * 40):
                for status in (" M source.sv", "M  staged.sv", " M nested", "?? untracked", None):
                    for dry_run in (False, True):
                        with self.subTest(revision=revision, status=status, dry_run=dry_run):
                            with patch("ara_verify.dependencies._git_output", side_effect=["true", revision, status]) as git, \
                                    patch("ara_verify.dependencies._run") as run:
                                with self.assertRaises(DependencyError):
                                    _sync_locked_tool(root, tool, dry_run)
                                git.assert_any_call(path, "status", "--porcelain=v1", "--ignore-submodules=none")
                                run.assert_not_called()

    def test_exact_clean_tool_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = LockedTool("riscv-dv-rvv1", "a" * 40, "https://example.com/tool.git", "main", Path("tool"))
            (root / tool.path / ".git").mkdir(parents=True)
            with patch("ara_verify.dependencies._git_output", side_effect=["true", tool.revision, ""]), \
                    patch("ara_verify.dependencies._run") as run, \
                    patch("ara_verify.dependencies.patch_state") as state:
                self.assertEqual(_sync_locked_tool(root, tool, False), ("tool:riscv-dv-rvv1", "unchanged"))
                run.assert_not_called()
                state.assert_not_called()
