#!/usr/bin/env python3
"""Host-only wrapper control tests. No RISC-V code or hardware is executed."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class EnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="resident-wrapper-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        for name in ("safety", "perf"):
            (self.bundle / name).mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.script(self.bin / "uname", '#!/bin/sh\nprintf "riscv64\\n"\n')
        self.script(self.bundle / "safety/lease_smoke.elf", '''#!/bin/sh
i=0
while [ "$i" -lt "${TEST_CASES:-11}" ]; do
    printf 'LEASE_SMOKE_WAIT case=%s forced=0 phases=1 pass=1\n' "$i"
    i=$((i + 1))
done
[ "${TEST_NO_DONE:-0}" = 1 ] || printf 'LEASE_SMOKE_DONE passed=11 total=11 errors=0 scope=bounded-safety-not-OS-proof\n'
exit "${TEST_SAFETY_RC:-0}"
''')
        self.script(self.bundle / "perf/run_board.sh", '''#!/bin/sh
[ "$ARA_DIRECT_PLATFORM_ACCEPTED" = yes ] || exit 99
mkdir "$1"
printf 'mock SDK runner entered\n' > "$1/mock-entry"
exit "${TEST_PERF_RC:-0}"
''')
        shutil.copyfile(HERE / "run_environment.sh", self.bundle / "run_environment.sh")
        (self.bundle / "kernel.sha256").write_text("a" * 64 + "\n")
        (self.bundle / "safety/SHA256SUMS").write_text("host fixture only\n")
        lines = []
        for path in sorted(self.bundle.rglob("*")):
            if path.is_file():
                lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " +
                             str(path.relative_to(self.bundle)) + "\n")
        (self.bundle / "SHA256SUMS").write_text("".join(lines))
        self.output = self.root / "results"
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        BOARD_ID="mock-board", BITSTREAM_SHA256="b" * 64, KERNEL_SHA256="a" * 64)

    def script(self, path, text):
        path.write_text(text)
        path.chmod(0o700)

    def run_wrapper(self, **updates):
        return subprocess.run(["sh", str(self.bundle / "run_environment.sh"), str(self.output)],
                              env=dict(self.env, **updates), text=True, capture_output=True,
                              timeout=10)

    def failed_before_perf(self, **updates):
        result = self.run_wrapper(**updates)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.output / "perf").exists())

    def test_success_requires_safety_then_perf(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "status").read_text(), "COMPLETE\n")
        self.assertTrue((self.output / "perf/mock-entry").is_file())

    def test_kernel_mismatch(self):
        self.failed_before_perf(KERNEL_SHA256="c" * 64)

    def test_missing_image_identity(self):
        self.failed_before_perf(BITSTREAM_SHA256="")

    def test_bundle_drift(self):
        (self.bundle / "kernel.sha256").write_text("a" * 64)
        self.failed_before_perf()

    def test_safety_failure_even_with_pass_markers(self):
        self.failed_before_perf(TEST_SAFETY_RC="1")
        self.assertEqual((self.output / "status").read_text(), "FAILED\n")

    def test_missing_case_record(self):
        self.failed_before_perf(TEST_CASES="10")

    def test_missing_completion(self):
        self.failed_before_perf(TEST_NO_DONE="1")

    def test_perf_failure_not_complete(self):
        result = self.run_wrapper(TEST_PERF_RC="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.output / "status").read_text(), "FAILED\n")

    def test_never_overwrite(self):
        self.output.mkdir()
        marker = self.output / "existing"
        marker.write_text("preserved")
        self.failed_before_perf()
        self.assertEqual(marker.read_text(), "preserved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
