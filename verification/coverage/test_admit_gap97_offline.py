"""Fail-closed GAP97 admission tests; actual runtime is read-only, no admission."""
import copy
import csv
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import admit_gap97_offline as tool


class Admission97Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = tool.elf_metadata((tool.runner.PRE / "input.elf").read_bytes())
        cls.rows = tool.commit_rows(tool.RUN / "commit_trace.csv")
        cls.actual = tool.runtime(tool.RUN, cls.meta, tool.runner.PRE / "spike.trace")

    def test_actual_runtime_without_writing_admission(self):
        self.assertEqual(self.actual["scalar"]["status"], "TERMINAL_TOHOST_MATCH")
        self.assertEqual(self.actual["scalar"]["matched_instructions"], 767)
        self.assertEqual(self.actual["vector"]["status"], "UNOBSERVABLE")
        self.assertEqual(self.actual["architecture"]["exact_observed_bytes"], 600)
        self.assertEqual(self.actual["architecture"]["checks"], 75)
        self.assertEqual(self.actual["handshakes"]["requests"], 85)
        self.assertFalse(self.actual["vector_data_scope"]["vector_comparison_pass"])

    def test_expected_merge_atomic_conflicts(self):
        book = tool.PinBook()
        book.merge({"/a": "a" * 64})
        with self.assertRaisesRegex(ValueError, "Expected-pin conflict"):
            book.merge({"/b": "b" * 64, "/a": "c" * 64})
        self.assertEqual(book.pins, {"/a": "a" * 64})
        book.merge({"/a": "a" * 64, "/b": "b" * 64})
        for invalid in ({}, {"relative": "a" * 64}, {"/bad": "not-a-hash"}):
            with self.assertRaises(ValueError):
                tool.PinBook().merge(invalid)

    def test_snapshot_and_rehash_cannot_replace_expected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sealed"
            path.write_bytes(b"before")
            book = tool.PinBook()
            book.merge({str(path): tool.preflight.sha(path)})
            expected = dict(book.pins)
            path.write_bytes(b"after")
            for call in (lambda: book.read(path), book.check):
                with self.assertRaisesRegex(ValueError, "Pinned evidence drift"):
                    call()
                self.assertEqual(book.pins, expected)

    def test_baseline_drift_stops_chain_before_runtime_or_output(self):
        with patch.object(tool.PinBook, "read", side_effect=ValueError("Pinned evidence drift")), \
                patch.object(tool, "runtime") as runtime:
            with self.assertRaisesRegex(ValueError, "Pinned evidence drift"):
                tool.prepare_chain()
            runtime.assert_not_called()

    def test_readonly_check_inputs_never_runtime_or_write(self):
        with patch.object(tool, "prepare_chain", return_value=(tool.PinBook(), {}, {}, {})), \
                patch.object(tool, "runtime") as runtime, patch.object(tool.preflight, "save") as save:
            tool.main(["check-inputs"])
            runtime.assert_not_called()
            save.assert_not_called()

    def test_elf_symbols_derived_and_wrong_metadata_rejected(self):
        blob = (tool.runner.PRE / "input.elf").read_bytes()
        self.assertEqual(self.meta["symbols"], tool.runner.SYMBOLS)
        for broken in (blob[:32], b"BAD!" + blob[4:], blob[:18] + b"\x00\x00" + blob[20:]):
            with self.assertRaises(ValueError):
                tool.elf_metadata(broken)
        with patch.dict(tool.runner.SYMBOLS, {"tohost": 0}, clear=False):
            with self.assertRaises(ValueError):
                tool.elf_metadata(blob)

    def test_csr_old_value_and_order_rejected(self):
        for phase in (0, 5, 9):
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows if r["event"] == "retire" and
                       r["pc"] == self.meta["symbols"]["gap97_probe%d" % phase])
            row["rd_wdata"] ^= 1
            with self.assertRaises(ValueError):
                tool.architecture_audit(rows, self.meta)
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows if r["event"] == "retire" and r["order"] == 20)
        row["order"] += 1
        with self.assertRaises(ValueError):
            tool.architecture_audit(rows, self.meta)

    def test_vset_return_and_post_configuration_reads_rejected(self):
        pc = self.meta["symbols"]["gap97_large_avl"]
        for mutate in (lambda r: r.update(rd_wdata=127), lambda r: r.update(insn=r["insn"] | (1 << 20))):
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows if r["event"] == "retire" and r["pc"] == pc)
            mutate(row)
            with self.assertRaises(ValueError):
                tool.architecture_audit(rows, self.meta)
        for read in self.actual["architecture"]["post_vset_csr_reads"]:
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows if r["event"] == "retire" and r["order"] == read["order"])
            row["rd_wdata"] ^= 1
            with self.assertRaises(ValueError):
                tool.architecture_audit(rows, self.meta)

    def test_exact_memory_and_store_lane_mask(self):
        for address in (self.meta["symbols"]["g97_observed"], self.meta["symbols"]["g97_avl"],
                        self.meta["symbols"]["g75_result"]):
            rows = copy.deepcopy(self.rows)
            row = [r for r in rows if r["event"] == "retire" and r["mem_addr"] == address and r["mem_wmask"]][-1]
            row["mem_wdata"] ^= 1
            with self.assertRaises(ValueError):
                tool.architecture_audit(rows, self.meta)
        rows = copy.deepcopy(self.rows)
        row = [r for r in rows if r["event"] == "retire" and
               r["mem_addr"] == self.meta["symbols"]["g75_result"] and r["mem_wmask"]][-1]
        row["mem_wmask"] = 0x0f
        with self.assertRaises(ValueError):
            tool.architecture_audit(rows, self.meta)

    def test_failed_tohost_and_incomplete_scalar_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[-1]["mem_wdata"] = 3
        with self.assertRaises(ValueError):
            tool.architecture_audit(rows, self.meta)
        for key, value in (("status", "PREFIX"), ("ara_trap_events", 1),
                           ("matched_instructions", 766), ("skipped_unobservable_register_values", 1)):
            scalar = copy.deepcopy(self.actual["scalar"])
            scalar[key] = value
            with self.assertRaises(ValueError):
                tool.validate_scalar(scalar, 767)

    def test_vset_handshake_missing_or_wrong_id_or_value(self):
        real = self.actual["handshakes"]["vset"]
        for event, field, value in (("cvx_req", "trans_id", (real["request"]["trans_id"] + 1) % 8),
                                    ("cvx_resp", "rd_wdata", 127), ("cvx_req", "insn", 0)):
            rows = copy.deepcopy(self.rows)
            matching = real["response"] if event == "cvx_resp" else real["request"]
            row = next(r for r in rows if r == matching)
            row[field] = value
            with self.assertRaises(ValueError):
                tool.handshake_audit(rows, self.actual["architecture"])
        rows = [r for r in self.rows if r != real["request"]]
        with self.assertRaises(ValueError):
            tool.handshake_audit(rows, self.actual["architecture"])

    def test_unobservable_not_relabelled_pass_and_exact_zero(self):
        tool.validate_vector(self.actual["vector"])
        for key, value in (("status", "PASS"), ("compared_bytes", 1), ("skipped_unknown_bytes", 1),
                           ("vector_destination_requests", 1), ("incomplete_requests", [1]),
                           ("unretired_requests", [1]), ("trapped_requests", [1])):
            vector = copy.deepcopy(self.actual["vector"])
            vector[key] = value
            with self.assertRaises(ValueError):
                tool.validate_vector(vector)

    def test_header_and_extra_vector_event_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vector.csv"
            path.write_text((tool.RUN / "vector_trace.csv").read_text().replace("vlen_bits", "wrong_field"))
            with self.assertRaises(ValueError):
                tool.read_csv(path, tool.VECTOR_FIELDS)
            path.write_text((tool.RUN / "vector_trace.csv").read_text() + "1,req,0\n")
            with self.assertRaises(ValueError):
                tool.read_csv(path, tool.VECTOR_FIELDS)

    def test_fresh_output_gate_never_reads_chain(self):
        with patch.object(tool, "prepare_chain") as chain:
            for output in (tool.BASE, Path("/tmp/gap97-rejected"), tool.OUT / ".." / "escape"):
                with self.assertRaises(ValueError):
                    tool.main(["admit", "--output", str(output)])
            chain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
