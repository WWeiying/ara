#!/usr/bin/env python3
"""Host-only planning/gate regressions. Never invokes a compiler or simulator."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_runtime_pack_projection as build
from run_half_scale_soc import check_projection_app, digest, hashes
from run_runtime_pack_projection import compare, completed_twin


def write_json(path, value):
    path.write_text(json.dumps(value))


class NativeGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "qbs_runtime.c"
        self.header = self.root / "qbs_pack_rvv_internal.h"
        files = [self.runtime, self.header, *[self.root / name for name in
                 ("run_runtime_activation_pack.py", "test_runtime_activation_pack.c",
                  "runtime_activation_pack_init.c")]]
        for file in files:
            file.write_text("sealed\n")
        self.pins = hashes(files)
        write_json(self.root / "manifest.json", self.pins)
        cases = []
        for mode, vlen, avl in (("scalar", 1024, 0), ("vector", 128, 0),
                                ("vector", 1024, 0), ("vector", 1024, 7)):
            label = f"{mode}-avl{avl}"
            log, elf = self.root / f"vlen{vlen}-{label}.log", self.root / f"init-{label}"
            log.write_text("RUNTIME_PACK_PASS cases=10752 invalid=8 bytes=exact "
                           "guards=exact fcsr_vcsr=exact\nRUNTIME_PACK_GUEST_EXIT=0\n")
            elf.write_bytes(b"test ELF")
            cases.append(dict(mode=mode, vlen=vlen, avl_limit=avl, cases=10752,
                              invalid_cases=8, log_sha256=digest(log), elf_sha256=digest(elf)))
        self.state = dict(state="PASS", child_pid=None, cases=cases)
        write_json(self.root / "status.json", self.state)
        for patcher in (patch.object(build, "RUNTIME", self.runtime),
                        patch.object(build, "HERE", self.root),
                        patch.object(build, "runtime_headers", return_value=[self.header])):
            patcher.start()
            self.addCleanup(patcher.stop)

    def check(self):
        return build.require_gate(self.root)

    def test_complete_gate(self):
        pins = self.check()
        self.assertIn(str(self.runtime), pins)
        self.assertIn(str(self.root / "vlen1024-vector-avl7.log"), pins)

    def test_running_gate_rejected(self):
        self.state["state"] = "running"
        write_json(self.root / "status.json", self.state)
        with self.assertRaisesRegex(ValueError, "not completed PASS"):
            self.check()

    def test_missing_or_duplicate_configuration_rejected(self):
        for cases in (self.state["cases"][:-1], self.state["cases"] * 2):
            write_json(self.root / "status.json", {**self.state, "cases": cases})
            with self.assertRaisesRegex(ValueError, "coverage"):
                self.check()

    def test_changed_runtime_rejected(self):
        self.runtime.write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.check()

    def test_missing_header_pin_rejected(self):
        del self.pins[str(self.header)]
        write_json(self.root / "manifest.json", self.pins)
        with self.assertRaisesRegex(ValueError, "all current"):
            self.check()

    def test_log_and_elf_changes_rejected(self):
        for name in ("vlen128-vector-avl0.log", "init-vector-avl0"):
            file = self.root / name
            previous = file.read_bytes()
            file.write_bytes(previous + b"mutation")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                self.check()
            file.write_bytes(previous)

    def test_hashed_fake_pass_rejected(self):
        log = self.root / "vlen128-vector-avl0.log"
        log.write_text("RUNTIME_PACK_GUEST_EXIT=0\n")
        self.state["cases"][1]["log_sha256"] = digest(log)
        write_json(self.root / "status.json", self.state)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.check()

    def test_wrong_case_count_rejected(self):
        self.state["cases"][1]["cases"] -= 1
        write_json(self.root / "status.json", self.state)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.check()


class PlanTests(unittest.TestCase):
    def test_relink_changes_only_paths(self):
        old = ["gcc", "-O2", "/old/a.o", "/old/runtime.o", "-Wl,-Map=/old/link.map",
               "-T", "/old/link.ld", "-lm", "-lgcc", "-o", "/old/app.elf"]
        replacements = {"/old/" + name: "/new/" + name for name in ("a.o", "runtime.o", "link.ld")}
        new = build.replace_link(old, replacements, Path("/new"))
        self.assertEqual(new, ["gcc", "-O2", "/new/a.o", "/new/runtime.o", "-Wl,-Map=/new/link.map",
                              "-T", "/new/link.ld", "-lm", "-lgcc", "-o", "/new/" + build.APP])
        self.assertEqual(old[-1], "/old/app.elf")
        self.assertFalse(any("wrap" in x for x in new))

    def test_disassembly_reports_nonpack_and_data_changes(self):
        old = build.disassembly_sections("file.o: file format elf64\n"
            "Disassembly of section .text.pack_activation_group.constprop.0:\n  old pack\n"
            "Disassembly of section .text.qbs_run:\n  old run\n"
            "Disassembly of section .rodata:\n  old data\n")
        new = {**old, ".text.pack_activation_group.constprop.0": "new pack",
               ".text.qbs_run": "new run", ".rodata": "new data"}
        self.assertEqual(build.section_changes(old, new)["non_pack_sections"],
                         [".rodata", ".text.qbs_run"])

    def test_no_disassembly_rejected(self):
        with self.assertRaisesRegex(ValueError, "No object"):
            build.disassembly_sections("file.o: file format elf64")


class ProjectionCheckerTests(unittest.TestCase):
    def test_direct_reads_include_quantization_input_and_descriptors(self):
        case = build.APP.removeprefix("llama_qwen25_")
        log = (f"QBS_REAL_PREFLIGHT case={case} layout=2 packed_bytes=3808 "
               "context_capacity=4672 tiles=28\n"
               f"QBS_REAL_ORACLE case={case} outputs=3584 quant_byte_mismatches=0 "
               "mismatches=0 kind=scalar_fp64_offline\n"
               f"QBS_REAL_BENCH case={case} k=896 rows=896 inputs=4 outputs=3584 tiles=28 "
               "operations=1 quantizations=1 cross_op_reuse=0 mismatches=0 result=PASS "
               "qbs_status=0 setup_included=1 activation_context=0 quantize_cycles=26056 "
               "pack_cycles=62462 matmul_cycles=168457 compute_cycles=256975 "
               "timed_cycles=256975 logical_read_bytes=974400\n")
        parsed = check_projection_app(log, build.APP)
        self.assertEqual(parsed["logical_read_components"], dict(quantization_input=14336,
                         descriptors=448, weights=852992, activations=106624))
        with self.assertRaisesRegex(RuntimeError, "logical reads"):
            check_projection_app(log.replace("974400", "960064"), build.APP)

    def test_pass_status_without_simulation_evidence_is_not_enough(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pin = root / "input"
            pin.write_text("sealed")
            write_json(root / "manifest.json", hashes([pin]))
            write_json(root / "status.json", dict(state="PASS", mode="scalar", child_pid=None,
                       manifest_sha256=digest(root / "manifest.json"), cases={}))
            with self.assertRaises(FileNotFoundError):
                completed_twin(root, "scalar", root, hashes([pin]))


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(image_pins_sha256="image", projection=dict(result=dict(
            checksum="same", k="896", rows="896", inputs="4", outputs="3584", tiles="28",
            operations="1", quantizations="1", activation_context="0", logical_read_bytes="974400",
            timing_scope="quant_pack_matmul", quantize_cycles="20", pack_cycles="30",
            matmul_cycles="50", timed_cycles="100")))

    def test_negative_performance_is_valid_measurement(self):
        after = copy.deepcopy(self.before)
        after["projection"]["result"].update(pack_cycles="40", timed_cycles="110")
        result = compare(self.before, after)
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(result["performance"], "regressed")
        self.assertFalse(result["deployment_approved"])
        self.assertEqual(result["total_cycle_change_percent"], 10)

    def test_neutral_performance(self):
        self.assertEqual(compare(self.before, self.before)["performance"], "neutral")

    def test_changed_output_or_work_rejected(self):
        for field in ("checksum", "outputs", "tiles", "logical_read_bytes", "timing_scope"):
            after = copy.deepcopy(self.before)
            after["projection"]["result"][field] = "different"
            with self.assertRaisesRegex(ValueError, "workload/output"):
                compare(self.before, after)

    def test_changed_image_rejected(self):
        with self.assertRaisesRegex(ValueError, "simulator"):
            compare(self.before, {**self.before, "image_pins_sha256": "different"})


if __name__ == "__main__":
    unittest.main()
