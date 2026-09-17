#!/usr/bin/env python3
"""Regression checks for source-version-sensitive FPGA integration patches."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export import (patch_akv_descriptor_reduction, patch_akv_byte_counts,
                    patch_dispatcher_vlen_casts, patch_qbs_fault_decode, replace_once)
from prepare import ROOT
from dispatcher_fpga import FUNCTIONS, HELPERS, NEW_UPDATE, OLD_UPDATE, patch_dispatcher_layout
from dispatcher_control_fpga import (dispatcher_edits, patch_dispatcher_control,
                                     patch_segment_geometry, segment_edits)
from jtag_fpga import patch_jtag, patch_tap, patch_reset_sync, patch_ready
from cdc_fpga import patch_reset_muxes


def frozen_file(path, revision="dec4174a"):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT, text=True)


class IntegrationPatchTests(unittest.TestCase):
    legacy = "if (read_completion_valid && !&descriptor_byte_valid_q) begin\n"
    current = "if (read_completion_valid && !(&descriptor_byte_valid_q)) begin\n"

    def test_legacy_akv_syntax(self):
        self.assertEqual(patch_akv_descriptor_reduction(self.legacy), self.current)

    def test_current_akv_is_unchanged(self):
        self.assertEqual(patch_akv_descriptor_reduction(self.current), self.current)

    def test_akv_patch_is_idempotent(self):
        once = patch_akv_descriptor_reduction(self.legacy)
        self.assertEqual(patch_akv_descriptor_reduction(once), once)

    def test_unexpected_akv_source_is_rejected(self):
        for source in ("", self.legacy * 2, self.current * 2,
                       self.legacy + self.current,
                       "if (!descriptor_byte_valid_q) begin\n"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(RuntimeError, "AKV descriptor reduction"):
                    patch_akv_descriptor_reduction(source)

    def test_other_patches_remain_strict(self):
        self.assertEqual(replace_once("before", "before", "after"), "after")
        for source in ("after", "before before"):
            with self.subTest(source=source):
                with self.assertRaises(RuntimeError):
                    replace_once(source, "before", "after")


class JtagPatchTests(unittest.TestCase):
    def test_frozen_sources_and_provenance(self):
        import re
        pkg = ROOT / "hardware/fpga/ara_dsa_vcu118"
        transforms = {"rtl/riscv-dbg/src/dmi_jtag.sv": patch_jtag,
                      "rtl/riscv-dbg/src/dmi_jtag_tap.sv": patch_tap,
                      "rtl/common_cells/src/rstgen_bypass.sv": lambda t: patch_reset_muxes(patch_reset_sync(t)),
                      "rtl/board/dram_wrapper_xilinx.sv": patch_ready}
        blocks = re.split(r"(?=^--- a/)", frozen_file(
            "hardware/fpga/ara_dsa_vcu118/provenance/integration.patch"), flags=re.M)
        for rel, transform in transforms.items():
            before = subprocess.check_output(["git", "show", "74042fbd:hardware/fpga/ara_dsa_vcu118/" + rel],
                                             cwd=ROOT, text=True)
            after = transform(before)
            self.assertEqual(after, (pkg / rel).read_text(), rel)
            with self.assertRaises(RuntimeError):
                transform("")
            with self.assertRaises(RuntimeError):
                transform(after)
            # Last block is the delta from the pinned FPGA baseline.
            patch = [b for b in blocks if b.startswith("--- a/" + rel + "\n")][-1]
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / rel
                target.parent.mkdir(parents=True)
                target.write_text(before)
                subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=patch,
                               text=True, cwd=directory, check=True, capture_output=True)
                self.assertEqual(target.read_text(), after)

    def test_sampled_tap_source_is_pinned(self):
        for transform in (patch_jtag, patch_tap):
            with self.assertRaises(RuntimeError):
                transform("unreviewed source")

    def test_jtag_evidence_matches_current_rtl(self):
        import hashlib
        import json
        directory = ROOT / "hardware/fpga/vcu118/results/20260916_jtag_reset"
        result = json.loads((directory / "result.json").read_text())
        for name, expected in result["inputs"].items():
            if name == "board_sha256":
                name = "hardware/fpga/ara_dsa_vcu118/rtl/board/ara_dsa_vcu118.sv"
            elif name == "dram_sha256":
                name = "hardware/fpga/ara_dsa_vcu118/rtl/board/dram_wrapper_xilinx.sv"
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected, name)
        log = (directory / "run.txt").read_bytes()
        self.assertEqual(hashlib.sha256(log).hexdigest(), result["run_sha256"])
        self.assertIn(b"74 scan checks, 45/45 DMI acceptances", log)
        self.assertIn(b"board reset CDC, 50 checks", log)


class DispatcherPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Test the reviewed export input, not concurrently changing main RTL.
        cls.source = subprocess.check_output([
            "git", "show", "74042fbd:hardware/src/ara_dispatcher.sv"
        ], cwd=ROOT, text=True)
        cls.patched = patch_dispatcher_vlen_casts(cls.source)

    def test_only_three_reported_lines_change(self):
        before, after = self.source.splitlines(), self.patched.splitlines()
        self.assertEqual(len(before), len(after))
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(len(changed), 3)
        for a, b in changed:
            self.assertEqual(b, a.replace("vlen_t'(acc_req_i.rs1)",
                                          "acc_req_i.rs1[$bits(csr_vl_d)-1:0]")
                                .replace("vlen_t'(ara_req.stride)",
                                         "ara_req.stride[$bits(csr_vl_q)-1:0]"))

    def test_overflow_guards_are_preserved(self):
        for guard, count in (("|acc_req_i.rs1[$bits(acc_req_i.rs1)-1:$bits(csr_vl_d)]", 1),
                             ("|ara_req.stride[$bits(ara_req.stride)-1:$bits(csr_vl_q)]", 2)):
            self.assertEqual(self.source.count(guard), count)
            self.assertEqual(self.patched.count(guard), count)

    def test_current_source_is_idempotent(self):
        self.assertEqual(patch_dispatcher_vlen_casts(self.patched), self.patched)

    def test_unexpected_source_is_rejected(self):
        missing = self.source.replace("vlen_t'(ara_req.stride)", "csr_vl_q", 1)
        mixed = self.source.replace("vlen_t'(ara_req.stride)",
                                    "ara_req.stride[$bits(csr_vl_q)-1:0]", 1)
        for source in ("", self.source * 2, missing, mixed):
            with self.subTest(source=source[:60]):
                with self.assertRaisesRegex(RuntimeError, "dispatcher VL comparison"):
                    patch_dispatcher_vlen_casts(source)


class DispatcherLayoutPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = subprocess.check_output([
            "git", "show", "74042fbd:hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/ara_dispatcher.sv"
        ], cwd=ROOT, text=True)
        cls.patched = patch_dispatcher_layout(cls.source)

    def test_legacy_snapshot_matches(self):
        exported = "hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/ara_dispatcher.sv"
        self.assertEqual(patch_dispatcher_control(self.patched), frozen_file(exported))

    def test_control_patch_is_reversible_and_strict(self):
        patched = patch_dispatcher_control(self.patched)
        self.assertEqual(dispatcher_edits(patched, reverse=True), self.patched)
        self.assertEqual(patch_dispatcher_control(patched), patched)
        for text in (self.patched + "\n", patched.replace("if (fpga_arch_decode)", "if (1'b1)")):
            with self.assertRaises(RuntimeError):
                patch_dispatcher_control(text)

    def test_segment_patch_is_reversible_and_strict(self):
        rel = "hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/segment_sequencer.sv"
        source = subprocess.check_output(["git", "show", "74042fbd:" + rel], cwd=ROOT, text=True)
        patched = patch_segment_geometry(source)
        self.assertEqual(patched, frozen_file(rel))
        self.assertEqual(segment_edits(patched, reverse=True), source)
        self.assertEqual(patch_segment_geometry(patched), patched)
        with self.assertRaises(RuntimeError):
            patch_segment_geometry(source.replace("next_vstart_cnt = vstart_cnt_q + 1;",
                                                  "next_vstart_cnt = vstart_cnt_q + 2;"))

    def test_segment_provenance_and_disabled_passthrough(self):
        import hashlib
        import json
        import re
        rel = "rtl/ara/hardware/src/segment_sequencer.sv"
        current = frozen_file("hardware/fpga/ara_dsa_vcu118/" + rel)
        raw = segment_edits(current, reverse=True)
        records = json.loads(frozen_file("hardware/fpga/ara_dsa_vcu118/manifest.json"))["source_hashes_before_integration"]
        expected = next(r["source_sha256"] for r in records if r["file"] == rel)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), expected)
        blocks = re.split(r"(?=^--- a/)", frozen_file(
            "hardware/fpga/ara_dsa_vcu118/provenance/integration.patch"), flags=re.M)
        patch = "".join(b for b in blocks if b.startswith("--- a/" + rel + "\n"))
        self.assertTrue(patch)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / rel
            target.parent.mkdir(parents=True)
            target.write_text(raw)
            subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=patch,
                           text=True, cwd=directory, check=True, capture_output=True)
            self.assertEqual(target.read_text(), current)
        self.assertIn("assign fpga_eew_req_o   = fpga_eew_req_i;",
                      current.split("end else begin : gen_no_segment_support", 1)[1])

    def test_control_patch_does_not_change_state_or_ee_writes_guard(self):
        patched = patch_dispatcher_control(self.patched)
        ff = self.patched.split("  always_ff", 1)[1].split("  end\n", 1)[0]
        self.assertIn(ff, patched)
        guard = "if (ara_req_valid_d && ara_req_d.use_vd && ara_req_ready_i &&\n        state_q != OVERLAP_PREFIX_FIXUP)"
        self.assertIn(guard, patched)
        special = patched.split("    // Special states\n", 1)[1].split(
            "    // Only these states can enter", 1)[0]
        self.assertNotRegex(special, r"\bara_req\b|\bara_req_valid\b")

    def test_recorded_control_check_matches_historical_snapshot(self):
        import hashlib
        import json
        directory = ROOT / "hardware/fpga/vcu118/results/20260915_dispatcher_control"
        record = json.loads((directory / "result.json").read_text())
        rtl = "hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/"
        for name, key in (("ara_dispatcher.sv", "after_sha256"),
                          ("segment_sequencer.sv", "segment_after_sha256")):
            self.assertEqual(hashlib.sha256(frozen_file(rtl + name).encode()).hexdigest(), record[key])
        for name, digest in record["logs_sha256"].items():
            log = (directory / name).read_bytes()
            self.assertEqual(hashlib.sha256(log).hexdigest(), digest)
            self.assertIn(b"equivalence PASS", log)
            self.assertNotIn(b"Fatal:", log)
        for name, digest in record["check_inputs_sha256"].items():
            self.assertEqual(hashlib.sha256(frozen_file(name).encode()).hexdigest(), digest)

    def test_only_reviewed_combinational_blocks_change(self):
        import re
        restored = self.patched.replace(HELPERS, "", 1).replace(NEW_UPDATE, OLD_UPDATE, 1)
        for name, (_, replacement) in FUNCTIONS.items():
            original = re.search(r"  function automatic [^\n]*\b" + name +
                                 r"\(.*?  endfunction : " + name, self.source, re.S).group()
            restored = restored.replace(replacement, original, 1)
        self.assertEqual(restored, self.source)

    def test_idempotent_and_fail_closed(self):
        self.assertEqual(patch_dispatcher_layout(self.patched), self.patched)
        changed = (
            self.source.replace("source_end -= 1;", "source_end -= 2;", 1),
            self.source.replace(OLD_UPDATE, "", 1),
            self.patched.replace("low = low - 1'b1;", "low = low - 2;", 1),
            self.patched + HELPERS,
        )
        for source in changed:
            with self.assertRaises(RuntimeError):
                patch_dispatcher_layout(source)

    def test_provenance_replays(self):
        import hashlib
        import json
        import re
        rel = "rtl/ara/hardware/src/ara_dispatcher.sv"
        raw = self.source.replace("acc_req_i.rs1[$bits(csr_vl_d)-1:0]",
                                  "vlen_t'(acc_req_i.rs1)").replace(
                                      "ara_req.stride[$bits(csr_vl_q)-1:0]", "vlen_t'(ara_req.stride)")
        records = json.loads(frozen_file("hardware/fpga/ara_dsa_vcu118/manifest.json"))["source_hashes_before_integration"]
        expected = next(r["source_sha256"] for r in records if r["file"] == rel)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), expected)
        patches = re.split(r"(?=^--- a/)", frozen_file(
            "hardware/fpga/ara_dsa_vcu118/provenance/integration.patch"), flags=re.M)
        patch_text = "".join(p for p in patches if p.startswith("--- a/" + rel + "\n"))
        self.assertTrue(patch_text)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / rel
            target.parent.mkdir(parents=True)
            target.write_text(raw)
            subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=patch_text,
                           text=True, cwd=directory, check=True, capture_output=True)
            self.assertEqual(target.read_text(), patch_dispatcher_control(self.patched))


class MainlineSyncTests(unittest.TestCase):
    revision = "db90e341"

    def test_integrated_dispatcher_and_segment_are_not_patched_twice(self):
        dispatcher = patch_dispatcher_vlen_casts(frozen_file(
            "hardware/src/ara_dispatcher.sv", self.revision))
        self.assertEqual(patch_dispatcher_layout(dispatcher), dispatcher)
        self.assertEqual(patch_dispatcher_control(dispatcher), dispatcher)
        segment = frozen_file("hardware/src/segment_sequencer.sv", self.revision)
        self.assertEqual(patch_segment_geometry(segment), segment)
        for transform, source in ((patch_dispatcher_layout, dispatcher),
                                  (patch_dispatcher_control, dispatcher),
                                  (patch_segment_geometry, segment)):
            with self.subTest(transform=transform.__name__):
                with self.assertRaises(RuntimeError):
                    transform(source + "\n")

    def test_exported_ara_matches_reviewed_mainline_with_fpga_patches(self):
        import hashlib
        import json
        pkg = ROOT / "hardware/fpga/ara_dsa_vcu118"
        manifest = json.loads((pkg / "manifest.json").read_text())
        evidence = json.loads((ROOT / "verification/timing/results/20260916_control_closure/summary.json").read_text())
        transforms = {
            "hardware/src/ara_dispatcher.sv": lambda t: patch_dispatcher_control(
                patch_dispatcher_layout(patch_dispatcher_vlen_casts(t))),
            "hardware/src/segment_sequencer.sv": patch_segment_geometry,
            "hardware/src/vlsu/qbs/qbs_engine.sv": patch_qbs_fault_decode,
            "hardware/src/vlsu/akv/akv_engine.sv": patch_akv_byte_counts,
        }
        checked = 0
        for record in manifest["source_hashes_before_integration"]:
            rel = record["file"]
            if not rel.startswith("rtl/ara/hardware/"):
                continue
            source_path = rel.removeprefix("rtl/ara/")
            raw = frozen_file(source_path, self.revision)
            digest = hashlib.sha256(raw.encode()).hexdigest()
            self.assertEqual(record["source_sha256"], digest, rel)
            self.assertEqual(evidence["source_sha256"][source_path], digest, rel)
            expected = transforms.get(source_path, lambda t: t)(raw)
            self.assertEqual((pkg / rel).read_text(), expected, rel)
            checked += 1
        self.assertEqual(checked, 54)

    def test_current_ara_provenance_replays(self):
        import re
        pkg = ROOT / "hardware/fpga/ara_dsa_vcu118"
        blocks = re.split(r"(?=^--- a/)", (pkg / "provenance/integration.patch").read_text(), flags=re.M)
        patched = set()
        with tempfile.TemporaryDirectory() as directory:
            for block in blocks:
                match = re.match(r"--- a/(rtl/ara/[^\n]+)\n", block)
                if not match:
                    continue
                rel = match[1]
                patched.add(rel)
                target = Path(directory) / rel
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(frozen_file(rel.removeprefix("rtl/ara/"), self.revision))
                subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=block,
                               text=True, cwd=directory, check=True, capture_output=True)
            for target in (Path(directory) / "rtl/ara").rglob("*.sv"):
                self.assertEqual(target.read_text(), (pkg / target.relative_to(directory)).read_text())
        self.assertEqual(patched, {
            "rtl/ara/hardware/src/vlsu/qbs/qbs_engine.sv",
            "rtl/ara/hardware/src/vlsu/akv/akv_engine.sv",
        })

    def test_current_dispatcher_evidence_matches_snapshot(self):
        import hashlib
        import json
        directory = ROOT / "hardware/fpga/vcu118/results/20260917_mainline_sync"
        record = json.loads((directory / "result.json").read_text())
        self.assertEqual(record["state"], "PASS")
        self.assertEqual(record["upstream"], self.revision)
        rtl = ROOT / "hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src"
        for name, key in (("ara_dispatcher.sv", "after_sha256"),
                          ("segment_sequencer.sv", "segment_after_sha256")):
            self.assertEqual(hashlib.sha256((rtl / name).read_bytes()).hexdigest(), record[key])
        log = (directory / "dispatcher_run.txt").read_text()
        self.assertIn(record["dispatcher_comparison"], log)
        self.assertIn(record["eew_metadata_comparison"], log)
        self.assertNotRegex(log, r"Fatal:|Error:")
        log = (directory / "layout_run.txt").read_text()
        for vlen, count in record["layout_vectors"].items():
            self.assertIn(f"PASS FPGA layout VLEN={vlen} checks={count}", log)
        self.assertNotRegex(log, r"Fatal:|Error:")


class AkvByteCountPatchTests(unittest.TestCase):
    def setUp(self):
        self.source = subprocess.check_output([
            "git", "show", "74042fbd:hardware/src/vlsu/akv/akv_engine.sv"
        ], cwd=ROOT, text=True)
        self.patched = patch_akv_byte_counts(self.source)

    def test_synthesis_countones_removed(self):
        body = self.patched.split("`ifndef SYNTHESIS", 1)[0]
        self.assertNotRegex(body, r"\$countones\(")
        self.assertEqual(self.patched.count("32'(fpga_read_data_byte_count)"), 2)

    def test_assertion_is_unchanged(self):
        self.assertEqual(self.source.split("`ifndef SYNTHESIS", 1)[1],
                         self.patched.split("`ifndef SYNTHESIS", 1)[1])

    def test_register_updates_only_change_count_expression(self):
        before = self.source[self.source.index("  always_ff"):]
        after = self.patched[self.patched.index("  always_ff"):]
        self.assertEqual(after, before.replace("32'($countones(read_data_strb))",
                                              "32'(fpga_read_data_byte_count)"))

    def test_changed_source_is_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_akv_byte_counts(self.source.replace("32'($countones(read_data_strb))", "0", 1))
        with self.assertRaises(RuntimeError):
            patch_akv_byte_counts(self.patched)


class QbsFaultPatchTests(unittest.TestCase):
    def setUp(self):
        self.source = subprocess.check_output([
            "git", "show", "74042fbd:hardware/src/vlsu/qbs/qbs_engine.sv"
        ], cwd=ROOT, text=True)

    def test_only_fault_decode_changes(self):
        patched = patch_qbs_fault_decode(self.source)
        start = patched.index("  // FPGA-only: one preserved LUT")
        end = patched.index("\n  );", start) + len("\n  );")
        original = """  assign compute_fault = state_q == QBS_ENGINE_COMPUTE_FAULT_DRAIN ||
      (state_q == QBS_ENGINE_RUN && read_fault_valid);"""
        self.assertEqual(patched[:start] + original + patched[end:], self.source)
        self.assertIn('(* DONT_TOUCH = "TRUE" *)', patched[start:end])
        self.assertIn('.I4(read_fault_valid), .O(compute_fault)', patched[start:end])
        self.assertNotIn("always_ff", patched[start:end])

    def test_changed_inputs_or_encoding_are_rejected(self):
        changed = [self.source.replace("&& read_fault_valid);", "&& read_busy);"),
                   self.source.replace("    QBS_ENGINE_RUN,", "    QBS_ENGINE_RUN = 12,"),
                   self.source.replace("typedef enum logic [3:0]", "typedef enum logic [4:0]", 1),
                   patch_qbs_fault_decode(self.source)]
        for source in changed:
            with self.subTest(source=source[:60]):
                with self.assertRaises(RuntimeError):
                    patch_qbs_fault_decode(source)


if __name__ == "__main__":
    unittest.main()
