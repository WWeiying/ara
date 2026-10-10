import os
import copy
import shlex
import signal
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import dve_tool_identity as tools


class ToolIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.wrapper = self.root / "bin/dve"
        self.runner = self.root / "xvfb-run"
        self.exe = self.root / "gui/dve/linux64/bin/dve.exe"
        self.arch = self.root / "gui/dve/bin/getarch_dve"
        for path in (self.wrapper, self.runner, self.exe, self.arch):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x7fELFtest" if path == self.exe else b"#!/bin/sh\n")
            path.chmod(0o755)

    def test_launcher_and_elf_are_both_sealed(self):
        result = tools.prepare(self.wrapper, self.runner)
        self.assertEqual(len(result["files"]), 4)
        self.assertEqual(result["executable"], str(self.exe))
        self.assertFalse(result["qualifies_previous_runs"])
        tools.revalidate(result)

    def test_changed_elf_rejected(self):
        result = tools.prepare(self.wrapper, self.runner)
        self.exe.write_bytes(b"\x7fELFchanged")
        with self.assertRaises(ValueError):
            tools.revalidate(result)

    def test_same_bytes_new_entity_rejected(self):
        result = tools.prepare(self.wrapper, self.runner)
        replacement = self.exe.with_suffix(".replacement")
        replacement.write_bytes(self.exe.read_bytes())
        replacement.chmod(0o755)
        replacement.replace(self.exe)
        with self.assertRaises(ValueError):
            tools.revalidate(result)

    def test_non_elf_rejected(self):
        self.exe.write_bytes(b"not an ELF")
        with self.assertRaises(ValueError):
            tools.prepare(self.wrapper, self.runner)

    def test_missing_architecture_selector_rejected(self):
        self.arch.unlink()
        with self.assertRaises(FileNotFoundError):
            tools.prepare(self.wrapper, self.runner)

    def test_wrapper_pid_not_confused_with_dve(self):
        result = tools.prepare(self.wrapper, self.runner)
        with self.assertRaises(ValueError):
            tools.verify_live_executable(os.getpid(), result, os.getpid(), 0)

    def test_empty_or_incomplete_files_rejected(self):
        result = tools.prepare(self.wrapper, self.runner)
        for files in ([], result["files"][:3]):
            changed = copy.deepcopy(result)
            changed["files"] = files
            with self.assertRaises(ValueError):
                tools.revalidate(changed)

    def test_modified_environment_and_roles_rejected(self):
        result = tools.prepare(self.wrapper, self.runner)
        changed = copy.deepcopy(result)
        changed["environment"]["DVE"] = "/tmp/other"
        with self.assertRaises(ValueError):
            tools.revalidate(changed)
        changed = copy.deepcopy(result)
        changed["roles"]["executable"] = str(self.wrapper)
        with self.assertRaises(ValueError):
            tools.revalidate(changed)

    def test_launcher_overrides_removed(self):
        result = tools.prepare(self.wrapper, self.runner)
        env = tools.controlled_environment(result, dict(DVE_USE_THIS_EXE="/tmp/other",
            DVE_USE_PURE_EXE="/tmp/pure", DVE="/tmp/tree", VERA_HOME="/tmp/vera",
            QADEBUG="1", LD_PRELOAD="/tmp/preload.so", ENV="/tmp/env",
            VCS_HOME="/tmp/vcs", VCS_TARGET_ARCH="linux", SNPSLMD_LICENSE_FILE="license",
            REPORT_FLAG="yes", NOGUI_FLAG="yes", REPORT_USE_THIS_EXE="/tmp/report",
            UCLI_USE_THIS_EXE="/tmp/ucli", PATH="/tmp/untrusted"))
        self.assertNotIn("DVE_USE_THIS_EXE", env)
        self.assertNotIn("DVE_USE_PURE_EXE", env)
        self.assertNotIn("QADEBUG", env)
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("ENV", env)
        for key in ("REPORT_FLAG", "NOGUI_FLAG", "REPORT_USE_THIS_EXE", "UCLI_USE_THIS_EXE"):
            self.assertNotIn(key, env)
        self.assertEqual(env["PATH"], "/usr/bin:/bin")
        self.assertEqual(env["VCS_HOME"], str(self.root))
        self.assertEqual(env["VCS_TARGET_ARCH"], "linux64")
        self.assertEqual(env["SNPSLMD_LICENSE_FILE"], "license")

    def test_launch_arguments_cannot_select_report_or_debug_binary(self):
        result = tools.prepare(self.wrapper, self.runner)
        command = tools.launch_command(result, self.arch)
        self.assertEqual(command[3:], ["-full64", "-cov", "-script", str(self.arch)])

    def test_bound_launch_child_positive(self):
        infos = {100: dict(parent=1, starttime=10),
                 101: dict(parent=100, starttime=11),
                 102: dict(parent=101, starttime=12)}
        with patch.object(tools, "process_info", side_effect=lambda pid: infos[pid]):
            self.assertEqual(tools.verify_launch_child(102, 100, 10), infos[102])

    def test_existing_other_process_and_reused_launch_pid_rejected(self):
        infos = {100: dict(parent=1, starttime=10),
                 101: dict(parent=1, starttime=11),
                 102: dict(parent=100, starttime=9)}
        with patch.object(tools, "process_info", side_effect=lambda pid: infos[pid]):
            for pid, start in ((101, 10), (102, 10), (101, 7)):
                with self.assertRaises(ValueError):
                    tools.verify_launch_child(pid, 100, start)

    def test_live_child_image_positive_without_eda(self):
        self.exe.unlink()
        self.exe.symlink_to(Path(sys.executable).resolve())
        record = tools.prepare(self.wrapper, self.runner)
        code = "import time; time.sleep(30)"
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)} & echo $!; wait"
        launch = subprocess.Popen(["/bin/sh", "-c", command], stdout=subprocess.PIPE,
                                  text=True, start_new_session=True)
        try:
            child = int(launch.stdout.readline())
            start = tools.process_info(launch.pid)["starttime"]
            result = tools.verify_live_executable(child, record, launch.pid, start)
            self.assertEqual(result["pid"], child)
            self.assertTrue(result["executable_verified"])
        finally:
            os.killpg(launch.pid, signal.SIGTERM)
            launch.wait(timeout=5)
            launch.stdout.close()


if __name__ == "__main__":
    unittest.main()
