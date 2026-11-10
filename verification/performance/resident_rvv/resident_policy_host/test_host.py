#!/usr/bin/env python3
"""Host-only admission/mapping tests; no native assembly, EDA or build wiring."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


class ResidentPolicyHostTest(unittest.TestCase):
    def build_and_run(self, extra_flags):
        with tempfile.TemporaryDirectory(prefix="akv-resident-policy-host-") as tmp:
            binary = Path(tmp) / "test_resident_policy"
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                "-fno-fast-math", "-ffp-contract=off", *extra_flags,
                "-I", str(ROOT), str(HERE / "test_resident_policy.c"),
                str(ROOT / "software/akv/src/akv_runtime.c"),
                "-lm", "-o", str(binary),
            ]
            built = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertIn("RESIDENT_POLICY_HOST_PASS schedules=1618 pairs=4051", ran.stdout)
            print(ran.stdout.strip(), flush=True)

    def test_optimized(self):
        self.build_and_run([])

    def test_undefined_behavior_sanitizer(self):
        self.build_and_run(["-O1", "-fsanitize=undefined", "-fno-sanitize-recover=all"])


if __name__ == "__main__":
    unittest.main()
