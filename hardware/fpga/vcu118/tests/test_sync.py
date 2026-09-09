#!/usr/bin/env python3
"""Filesystem regression for FPGA package synchronization; no Vivado needed."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import sync


def put(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and p.name != sync.SUMS}


def seal(root):
    values = hashes(root)
    put(root, sync.SUMS, "".join(f"{values[n]}  {n}\n" for n in sorted(values)))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fpga sync test ")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.target, self.source = root / "target", root / "incoming"
        self.manifest = {"top": "ara_dsa_vcu118", "part": "xcvu9p",
                         "files": ["rtl/ara/a.sv", "rtl/ara/old.sv"], "defines": {"ARA": None}}
        put(self.target, "manifest.json", json.dumps(self.manifest))
        put(self.target, "scripts/sources.tcl", "set rtl_files {}\n")
        put(self.target, "rtl/ara/a.sv", "original\n")
        put(self.target, "rtl/ara/old.sv", "old module\n")
        seal(self.target)
        shutil.copytree(self.target, self.source)

    def plan(self):
        return sync.make_plan(self.target, self.source)

    def test_noop(self):
        before = {p: p.stat().st_mtime_ns for p in self.target.rglob("*") if p.is_file()}
        self.assertIsNone(sync.apply_plan(self.target, self.source, self.plan()))
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in before})
        self.assertFalse((self.target / ".fpga_sync_backups").exists())

    def test_repository_default_target(self):
        from prepare import ROOT
        self.assertTrue((ROOT / "hardware/src/ara_dispatcher.sv").is_file())
        self.assertEqual(sync.DEFAULT_TARGET, ROOT / "hardware/fpga/ara_dsa_vcu118")

    def test_git_metadata_is_managed(self):
        for name, content in ((".gitattributes", "* -text\n"), (".gitignore", "/build/\n")):
            put(self.source, name, content)
        seal(self.source)
        plan = self.plan()
        self.assertEqual(set(plan["actions"]), {("ADD", ".gitattributes"), ("ADD", ".gitignore")})
        sync.apply_plan(self.target, self.source, plan)
        self.assertEqual((self.target / ".gitattributes").read_text(), "* -text\n")
        self.assertIn(".gitattributes", sync.read_hashes(self.target))
        put(self.target, ".gitignore", "local policy\n")
        self.assertEqual(self.plan()["local"], [".gitignore"])

    def test_cli_dry_run(self):
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        before = hashes(self.target)
        result = subprocess.run([sys.executable, str(HERE / "sync.py"), str(self.target),
                                 "--from-package", str(self.source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        self.assertEqual(hashes(self.target), before)
        self.assertFalse((self.target / ".fpga_sync_backups").exists())

    def test_update_add_delete_and_keep_outputs(self):
        put(self.target, "docs/rtl_static.log", "historical\n")
        seal(self.target)
        for name in ["build/top.xpr", "reports/synth.rpt", "output/top.bit", "rtl/ara/user.sv"]:
            put(self.target, name, "user data\n")
        put(self.source, "rtl/ara/a.sv", "updated\n")
        put(self.source, "rtl/ara/new.sv", "added\n")
        (self.source / "rtl/ara/old.sv").unlink()
        seal(self.source)
        plan = self.plan()
        self.assertEqual(set(plan["actions"]), {("UPDATE", "rtl/ara/a.sv"),
                         ("ADD", "rtl/ara/new.sv"), ("DELETE", "rtl/ara/old.sv")})
        backup = sync.apply_plan(self.target, self.source, plan)
        self.assertEqual((backup / "files/rtl/ara/a.sv").read_text(), "original\n")
        self.assertEqual((backup / "files/rtl/ara/old.sv").read_text(), "old module\n")
        self.assertEqual((self.target / "rtl/ara/new.sv").read_text(), "added\n")
        self.assertFalse((self.target / "rtl/ara/old.sv").exists())
        for name in ["build/top.xpr", "reports/synth.rpt", "output/top.bit", "rtl/ara/user.sv"]:
            self.assertEqual((self.target / name).read_text(), "user data\n")
            self.assertNotIn(name, sync.read_hashes(self.target))
        self.assertEqual((self.target / "docs/rtl_static.log").read_text(), "historical\n")
        self.assertFalse(self.plan()["actions"])

    def test_local_only_then_upstream_conflict(self):
        old = sync.read_hashes(self.target)["rtl/ara/a.sv"]
        put(self.target, "rtl/ara/a.sv", "local edit\n")
        put(self.source, "rtl/ara/old.sv", "another upstream edit\n")
        seal(self.source)
        plan = self.plan()
        self.assertEqual(plan["local"], ["rtl/ara/a.sv"])
        sync.apply_plan(self.target, self.source, plan)
        self.assertEqual(sync.read_hashes(self.target)["rtl/ara/a.sv"], old)
        put(self.source, "rtl/ara/a.sv", "upstream edit\n")
        seal(self.source)
        self.assertEqual(self.plan()["conflicts"], ["rtl/ara/a.sv"])

    def test_identical_dual_edit_adopts_baseline(self):
        for root in (self.target, self.source):
            put(root, "rtl/ara/a.sv", "same edit\n")
        seal(self.source)
        plan = self.plan()
        self.assertFalse(plan["actions"])
        self.assertEqual(plan["adopt"], ["rtl/ara/a.sv"])
        sync.apply_plan(self.target, self.source, plan)
        self.assertFalse(self.plan()["adopt"])

    def test_conflict_blocks_entire_apply(self):
        put(self.target, "rtl/ara/a.sv", "local\n")
        put(self.source, "rtl/ara/a.sv", "upstream\n")
        put(self.source, "rtl/ara/old.sv", "otherwise safe change\n")
        seal(self.source)
        before = hashes(self.target)
        with self.assertRaisesRegex(RuntimeError, "Conflicts"):
            sync.apply_plan(self.target, self.source, self.plan())
        self.assertEqual(hashes(self.target), before)
        self.assertFalse((self.target / ".fpga_sync_backups").exists())

    def test_local_deleted_preserved_then_conflicts(self):
        (self.target / "rtl/ara/a.sv").unlink()
        self.assertEqual(self.plan()["local"], ["rtl/ara/a.sv"])
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        self.assertEqual(self.plan()["conflicts"], ["rtl/ara/a.sv"])

    def test_upstream_delete_local_edit_conflict(self):
        put(self.target, "rtl/ara/a.sv", "local\n")
        (self.source / "rtl/ara/a.sv").unlink()
        seal(self.source)
        self.assertEqual(self.plan()["conflicts"], ["rtl/ara/a.sv"])

    def test_untracked_collision(self):
        put(self.target, "rtl/ara/new.sv", "local\n")
        put(self.source, "rtl/ara/new.sv", "incoming\n")
        seal(self.source)
        self.assertEqual(self.plan()["conflicts"], ["rtl/ara/new.sv"])

    def test_bad_incoming_hash_rejected(self):
        put(self.source, "rtl/ara/a.sv", "unsealed edit\n")
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            self.plan()

    def test_file_in_new_parent_path_rejected(self):
        put(self.target, "rtl/user", "untracked file\n")
        put(self.source, "rtl/user/new.sv", "new\n")
        seal(self.source)
        with self.assertRaisesRegex(RuntimeError, "Non-directory parent"):
            self.plan()

    def test_unsafe_checksum_path_rejected(self):
        for name in ["../outside", "/tmp/file", "C:/file", "rtl/../file", ".", "rtl/aux.sv"]:
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                sync.validate_name(name)

    def test_symlink_parent_rejected(self):
        outside = self.target.parent / "outside"
        shutil.move(str(self.target / "rtl/ara"), outside)
        (self.target / "rtl/ara").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.plan()
        self.assertEqual((outside / "a.sv").read_text(), "original\n")

    def test_windows_case_collision(self):
        put(self.target, "rtl/ARA/user.sv", "local\n")
        with self.assertRaisesRegex(RuntimeError, "case collision"):
            self.plan()

    def test_target_changed_after_preview(self):
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        plan = self.plan()
        put(self.target, "rtl/ara/a.sv", "concurrent local edit\n")
        with self.assertRaisesRegex(RuntimeError, "Target changed"):
            sync.apply_plan(self.target, self.source, plan)

    def test_source_changed_after_preview(self):
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        plan = self.plan()
        put(self.source, "rtl/ara/a.sv", "different incoming\n")
        seal(self.source)
        with self.assertRaisesRegex(RuntimeError, "Incoming checksum baseline changed"):
            sync.apply_plan(self.target, self.source, plan)

    def test_source_payload_changed_after_preview(self):
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        plan = self.plan()
        put(self.source, "rtl/ara/a.sv", "unsealed later edit\n")
        with self.assertRaisesRegex(RuntimeError, "Incoming source changed"):
            sync.apply_plan(self.target, self.source, plan)

    def test_standalone_copy_with_isolated_python(self):
        script = self.source / "scripts/sync.py"
        shutil.copyfile(HERE / "sync.py", script)
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        result = subprocess.run([sys.executable, "-I", str(script), str(self.target),
                                 "--from-package", str(self.source), "--apply"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "rtl/ara/a.sv").read_text(), "new\n")
        self.assertEqual((self.target / "scripts/sync.py").read_bytes(), script.read_bytes())

    def test_existing_permissions_preserved(self):
        original = self.target / "rtl/ara/a.sv"
        original.chmod(0o640)
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        sync.apply_plan(self.target, self.source, self.plan())
        self.assertEqual(original.stat().st_mode & 0o777, 0o640)

    def test_write_failure_rolls_back(self):
        put(self.source, "rtl/ara/a.sv", "new\n")
        put(self.source, "rtl/ara/new.sv", "new module\n")
        seal(self.source)
        before, old_sums = hashes(self.target), (self.target / sync.SUMS).read_bytes()
        real_write = sync.atomic_write
        def fail_second(path, data):
            if path.name == "new.sv":
                raise OSError("injected write error")
            real_write(path, data)
        with patch.object(sync, "atomic_write", side_effect=fail_second), self.assertRaises(OSError):
            sync.apply_plan(self.target, self.source, self.plan())
        self.assertEqual((self.target / sync.SUMS).read_bytes(), old_sums)
        for name, value in before.items():
            self.assertEqual(sync.digest(self.target / name), value)
        self.assertFalse((self.target / "rtl/ara/new.sv").exists())
        self.assertFalse((self.target / ".fpga_sync.lock").exists())
        journal, = (self.target / ".fpga_sync_backups").glob("*/record.json")
        self.assertEqual(json.loads(journal.read_text())["status"], "rolled_back")

    def test_existing_lock_is_not_removed(self):
        put(self.target, ".fpga_sync.lock", "existing job\n")
        put(self.source, "rtl/ara/a.sv", "new\n")
        seal(self.source)
        with self.assertRaisesRegex(RuntimeError, "Sync lock exists"):
            sync.apply_plan(self.target, self.source, self.plan())
        self.assertTrue((self.target / ".fpga_sync.lock").exists())

    def test_both_deleted_adopts(self):
        for root in (self.target, self.source):
            (root / "rtl/ara/a.sv").unlink()
        seal(self.source)
        sync.apply_plan(self.target, self.source, self.plan())
        self.assertNotIn("rtl/ara/a.sv", sync.read_hashes(self.target))

    def test_manifest_change_requires_project_refresh(self):
        self.manifest["files"].append("rtl/ara/new.sv")
        put(self.source, "manifest.json", json.dumps(self.manifest))
        put(self.source, "rtl/ara/new.sv", "new\n")
        seal(self.source)
        self.assertTrue(self.plan()["config_changed"])


class SmokeReuseTests(unittest.TestCase):
    def test_unchanged_input_uses_verified_outputs(self):
        import export
        with tempfile.TemporaryDirectory() as temp:
            previous, incoming = Path(temp) / "old", Path(temp) / "new"
            for name in export.SMOKE_INPUTS:
                put(previous, "software/" + name, "input\n")
                put(incoming, "software/" + name, "input\n")
            for name in export.SMOKE_OUTPUTS:
                put(previous, "software/" + name, "output\n")
            seal(previous)
            put(previous, "software/smoke.c", "local edit must not churn upstream binary\n")
            with patch.object(export.subprocess, "run") as command:
                export.build_or_reuse_smoke(incoming, "gcc", "objdump", previous)
                command.assert_not_called()
            self.assertEqual((incoming / "software/smoke.elf").read_text(), "output\n")
            put(incoming, "software/smoke.c", "new upstream input\n")
            with patch.object(export.subprocess, "run") as command:
                export.build_or_reuse_smoke(incoming, "gcc", "objdump", previous)
                command.assert_called_once()


if __name__ == "__main__":
    unittest.main()
