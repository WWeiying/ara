#!/usr/bin/env python3
"""Regression checks for source-version-sensitive FPGA integration patches."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export import (patch_akv_descriptor_reduction, patch_akv_byte_counts,
                    patch_dispatcher_vlen_casts, replace_once)
from prepare import ROOT


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


class DispatcherPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
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


class AkvByteCountPatchTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "hardware/src/vlsu/akv/akv_engine.sv").read_text()
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


if __name__ == "__main__":
    unittest.main()
