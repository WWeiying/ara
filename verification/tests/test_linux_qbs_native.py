"""Host unit tests; these are not native execution evidence."""

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "linux"))
import qbs_build as build
import qbs_run as run


class QbsPrerequisiteTests(unittest.TestCase):
    def test_quantize_zero(self):
        self.assertEqual(build.quantize(bytes(6144)), bytes(1752))

    def test_quantize_signed_peak_and_sums(self):
        result = build.quantize(struct.pack("<1536f", *([1.0] * 1536)))
        block = struct.unpack("<f256b16h", result[:292])
        self.assertAlmostEqual(block[0], -1 / 127)
        self.assertEqual(block[1:257], (-127,) * 256)
        self.assertEqual(block[257:], (-2032,) * 16)

    def test_quantize_bad_inputs(self):
        for data in (bytes(4), struct.pack("<f", float("nan")) + bytes(6140)):
            with self.assertRaises(ValueError):
                build.quantize(data)

    def test_capture_frozen_independently(self):
        root = build.OUT / "test-tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            frozen = build.freeze_capture(build.CAPTURE, Path(temporary) / "data")
            self.assertEqual(frozen["files"]["weight.bin"]["bytes"], 27648)
            self.assertEqual(frozen["files"]["golden.bin"]["bytes"], 128)
            golden = Path(frozen["files"]["golden.bin"]["path"])
            self.assertEqual(golden.read_bytes(), (build.CAPTURE / "output_f32.bin").read_bytes()[:128])
            golden.write_bytes(bytes(128))
            with self.assertRaises(ValueError):
                build.verify_record(frozen["files"]["golden.bin"])

    def test_capture_metadata_rejected(self):
        root = build.OUT / "test-tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            path = Path(temporary)
            (path / "weight_q4_K.json").write_text(json.dumps(
                {"type": "q4_K", "shape": [1], "strides": [1], "nbytes": 1}))
            with self.assertRaises(ValueError):
                build.freeze_capture(path, path / "data")

    @staticmethod
    def native_log():
        lines = ["[QBS_INIT] HASHES PASS", "[QBS_INIT] mode=native rc=0",
                 "OS_CUSTOM_CONTEXT=NOT_VALIDATED", "AKV_NATIVE_COMPUTE=UNAVAILABLE",
                 "[QBS] QUANTIZATION byte_exact=1752",
                 "[QBS] GUARDS inputs_unchanged=1 guards=8/8",
                 "[QBS_HOST_TRACE] info_entries=23 exec_entries=1",
                 "[QBS_HOST_TRACE] helper_qbs_exec entry=1",
                 "[QBS] COUNTS query_calls=23 native_calls=1",
                 "[QBS] CAPABILITY ok", "[QBS] ABI arch=3 desc=2 numerical=1 max_n=32",
                 "[QBS] PLAN emitted_commands=1 M=1 N=32 K_blocks=6 DIRECT",
                 "[QBS] PRECHECK capacity_alignment_rejected native_calls=0 unchanged=1",
                 "[QBS] NATIVE_RETURN status=ok", "QBS_NATIVE_COMPUTE=PASS"]
        lines += [f"[QBS] COMPARE {name} mismatches=0/32 max_abs=0 atol=0.002 rtol=0.002"
                  for name in ("rvv_frozen", "native_frozen", "native_rvv")]
        lines += [f"[QBS] OUTPUT index={i} bits=3f800000 golden=1" for i in range(32)]
        return "\n".join(lines)

    def test_complete_native_checker(self):
        result = run.check_console("native", self.native_log(), struct.pack("<32f", *([1] * 32)))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["OS_CUSTOM_CONTEXT"], "NOT_VALIDATED")

    def test_checker_rejects_incomplete_or_false_evidence(self):
        text = self.native_log()
        bad = [text.replace("exec_entries=1", "exec_entries=0"),
               text.replace("bits=3f800000", "bits=7fc00000", 1),
               text.replace("bits=3f800000", "bits=40000000", 1),
               text.replace("index=31", "index=30"),
               text.replace("guards=8/8", "guards=7/8"),
               text.replace("OS_CUSTOM_CONTEXT=NOT_VALIDATED", "OS_CUSTOM_CONTEXT=PASS"),
               text.replace("mismatches=0/32", "mismatches=1/32", 1),
               text + "\nQBS_NATIVE_COMPUTE=PASS",
               text + "\n[QBS] FAIL test"]
        for value in bad:
            with self.subTest(value=value[-100:]), self.assertRaises(ValueError):
                run.check_console("native", value, struct.pack("<32f", *([1] * 32)))

    def test_query_only_never_native(self):
        with self.assertRaises(ValueError):
            run.check_console("native", "[QBS] CAPABILITY ok\nQBS_NATIVE_COMPUTE=PASS", bytes(128))

    def test_planner_limits_are_not_emitted_tile(self):
        root = build.OUT / "test-tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            binary = Path(temporary) / "qbs_plan_check"
            subprocess.run(["gcc", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-I", str(build.REPO_ROOT / "software/qbs/include"),
                            str(build.LINUX / "qbs_plan_check.c"),
                            str(build.REPO_ROOT / "software/qbs/src/qbs_runtime.c"),
                            "-o", str(binary)], check=True, timeout=30,
                           env={"PATH": os.environ["PATH"], "TMPDIR": temporary})
            completed = subprocess.run([str(binary)], check=True, capture_output=True,
                                       text=True, timeout=5)
            self.assertIn("commands=1", completed.stdout)

    def test_controls_checker(self):
        for mode in ("fallback", "unsupported"):
            text = self.native_log()
            remove = ("[QBS] OUTPUT", "[QBS] ABI", "[QBS] PLAN", "[QBS] PRECHECK",
                      "[QBS] NATIVE_RETURN", "[QBS_HOST_TRACE] helper_qbs_exec",
                      "[QBS] COMPARE native_")
            text = "\n".join(line for line in text.splitlines() if not line.startswith(remove))
            text = text.replace("mode=native", f"mode={mode}")
            text = text.replace("info_entries=23 exec_entries=1", "info_entries=0 exec_entries=0")
            text = text.replace("QBS_NATIVE_COMPUTE=PASS", "QBS_NATIVE_COMPUTE=NOT_RUN\nRVV_FALLBACK=PASS")
            if mode == "fallback":
                text = text.replace("[QBS] CAPABILITY ok", "[QBS] CAPABILITY disabled")
                text = text.replace("query_calls=23 native_calls=1", "query_calls=0 native_calls=0")
            else:
                text = text.replace("[QBS] CAPABILITY ok", "[QBS] CAPABILITY unavailable signal=SIGILL")
                text = text.replace("query_calls=23 native_calls=1", "query_calls=1 native_calls=0")
                text += ("\nOS_CUSTOM_CONTEXT=NOT_VALIDATED\nAKV_NATIVE_COMPUTE=UNAVAILABLE"
                         "\n[QBS] CAPABILITY unavailable signal=SIGILL\nQBS_NATIVE_COMPUTE=UNSUPPORTED"
                         "\n[QBS] COUNTS query_calls=1 native_calls=0\n[QBS_INIT] auto_rc=0 require_rc=77")
            self.assertEqual(run.check_console(mode, text, bytes(128))["status"], "PASS")
            with self.assertRaises(ValueError):
                run.check_console(mode, text + "\nQBS_NATIVE_COMPUTE=PASS", bytes(128))

    def test_attempt_cannot_escape_output(self):
        for attempt in ("../other", "/tmp/escape", "attempt-1/../../other"):
            with self.assertRaises(ValueError):
                build.experiment_root(attempt)

    def test_elf_rejects_host_binary(self):
        with self.assertRaises(ValueError):
            build.validate_elf(Path(sys.executable).resolve(), "", "")


if __name__ == "__main__":
    unittest.main()
