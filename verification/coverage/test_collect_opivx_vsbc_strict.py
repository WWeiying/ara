"""Strict rejection tests using the complete actual VSBC terminal logs; no EDA."""
from copy import deepcopy
import json
import unittest

import collect_opivx_vsbc_strict as c


class ActualTerminalFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = c.life.read_bound(c.runner.PRE / "preflight-manifest.json", c.PRE_SEAL)
        cls.symbols = cls.pre["symbols"]
        cls.rows = c.read_csv((c.RUN / "commit_trace.csv").read_bytes(), c.COMMIT_FIELDS)
        cls.vectors = c.read_csv((c.RUN / "vector_trace.csv").read_bytes(), c.VECTOR_FIELDS)
        cls.tracer = (c.RUN / "trace_hart_0.log").read_text()
        cls.reference = c.software.parse_spike_commits(c.runner.PRE / "spike.trace")
        cls.expected = c.reference_counts(cls.reference, cls.symbols)
        cls.scalar = c.spike_trace.compare_commit_prefix(c.runner.PRE / "spike.trace", c.RUN / "commit_trace.csv",
            0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout="unshifted")
        cls.vector = c.compare_vector_commits(c.runner.PRE / "spike.trace", c.RUN / "commit_trace.csv",
                                             c.RUN / "vector_trace.csv", 0x80000000)
        cls.bad = next(int(r["order"]) for r in cls.rows if r["event"] == "arch_start" and int(r["insn"], 16) == c.BAD)
        cls.good = next(int(r["order"]) for r in cls.rows if r["event"] == "arch_start" and int(r["insn"], 16) == c.RECOVERY)
        cls.before = json.loads((c.BASE / "combined-bits.json").read_text())

    def test_actual_scalar_full(self):
        c.scalar_exact(self.scalar, self.expected)

    def test_actual_vector_full(self):
        c.vector_exact(self.vector, self.bad, self.reference)

    def test_actual_lifecycle(self):
        result = c.lifecycle(self.rows, self.vectors, self.symbols)
        self.assertEqual((result["requests"], result["responses"], result["exceptions"]), (32, 32, 1))

    def test_actual_all_signatures(self):
        result = c.observed(self.rows, self.symbols)
        self.assertEqual(result["explicit_dump_read_bytes"], 864)

    def test_actual_tracer_exception(self):
        self.assertEqual(c.tracer_exact(self.tracer, self.rows, self.symbols)["cause"], 2)

    def test_scalar_prefix_rejected(self):
        result = dict(self.scalar, status="PREFIX")
        with self.assertRaises(ValueError): c.scalar_exact(result, self.expected)

    def test_scalar_unknown_skip_rejected(self):
        result = dict(self.scalar, skipped_unobservable_register_values=1)
        with self.assertRaises(ValueError): c.scalar_exact(result, self.expected)

    def test_scalar_missing_instruction_rejected(self):
        result = dict(self.scalar, matched_instructions=self.expected["matched_instructions"] - 1)
        with self.assertRaises(ValueError): c.scalar_exact(result, self.expected)

    def test_vector_prefix_rejected(self):
        result = dict(self.vector, selected_index=1)
        with self.assertRaises(ValueError): c.vector_exact(result, self.bad, self.reference)

    def test_vector_unknown_byte_rejected(self):
        result = dict(self.vector, skipped_unknown_bytes=1)
        with self.assertRaises(ValueError): c.vector_exact(result, self.bad, self.reference)

    def test_vector_missing_init_byte_rejected(self):
        result = deepcopy(self.vector); result["instructions"][0]["compared_bytes"] -= 1
        with self.assertRaises(ValueError): c.vector_exact(result, self.bad, self.reference)

    def test_vector_wrong_recovery_pc_rejected(self):
        result = deepcopy(self.vector); result["instructions"][-1]["pc"] = "0x80000000"
        with self.assertRaises(ValueError): c.vector_exact(result, self.bad, self.reference)

    def test_illegal_backend_allocation_rejected(self):
        rows = deepcopy(self.rows)
        for event in ("uop_alloc", "uop_done"):
            row = dict(next(r for r in rows if r["event"] == event), order=str(self.bad))
            rows.append(row)
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.symbols)

    def test_illegal_vector_activity_rejected(self):
        vectors = deepcopy(self.vectors)
        vectors.append(dict(vectors[0], arch_seq=str(self.bad)))
        with self.assertRaises(ValueError): c.lifecycle(self.rows, vectors, self.symbols)

    def test_missing_response_rejected(self):
        rows = deepcopy(self.rows)
        rows.remove(next(r for r in rows if r["event"] == "cvx_resp"))
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.symbols)

    def test_duplicate_start_rejected(self):
        rows = deepcopy(self.rows)
        rows.append(dict(next(r for r in rows if r["event"] == "arch_start")))
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.symbols)

    def test_extra_exception_rejected(self):
        rows = deepcopy(self.rows)
        good_response = next(r for r in rows if r["event"] == "cvx_resp" and not int(r["trap"]))
        good_response["trap"] = "1"
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.symbols)

    def corrupt_store(self, name, offset, value):
        rows = deepcopy(self.rows); address = self.symbols[name] + offset
        match = [r for r in rows if r["event"] == "retire" and int(r["mem_addr"], 16) == address and int(r["mem_wmask"], 16)]
        self.assertTrue(match)
        match[-1]["mem_wdata"] = "%016x" % value
        with self.assertRaises(ValueError): c.observed(rows, self.symbols)

    def test_trap_cause_rejected(self):
        self.corrupt_store("gvs_ledger", 0, 4)

    def test_trap_tval_rejected(self):
        self.corrupt_store("gvs_ledger", 16, 0)

    def test_trap_vstart_rejected(self):
        self.corrupt_store("gvs_ledger", 40, 0)

    def test_post_mret_vstart_rejected(self):
        self.corrupt_store("gvs_post", 32, 0)

    def test_handler_t2_rejected(self):
        self.corrupt_store("gvs_post", 16, 4)

    def corrupt_dump_load(self, offset):
        rows = deepcopy(self.rows); address = self.symbols["gvs_dump"] + offset
        matches = [r for r in rows if r["event"] == "retire" and int(r["mem_addr"], 16) == address and int(r["mem_rmask"], 16)]
        self.assertTrue(matches)
        for row in matches: row["rd_wdata"] = "0000000000000000"
        with self.assertRaises(ValueError): c.observed(rows, self.symbols)

    def test_guard_readback_rejected(self):
        self.corrupt_dump_load(0)

    def test_recovery_tail_rejected(self):
        self.corrupt_dump_load((5 * 18 + 16) * 8)

    def test_incomplete_readback_rejected(self):
        rows = deepcopy(self.rows)
        address = self.symbols["gvs_dump"]
        for row in rows:
            if row["event"] == "retire" and int(row["mem_addr"], 16) == address and int(row["mem_rmask"], 16):
                row["mem_addr"] = "%016x" % (address + 8)
        with self.assertRaises(ValueError): c.observed(rows, self.symbols)

    def test_missing_terminal_rejected(self):
        rows = deepcopy(self.rows)
        rows.remove([r for r in rows if r["event"] == "retire"][-1])
        with self.assertRaises(ValueError): c.observed(rows, self.symbols)

    def test_tracer_bad_tval_rejected(self):
        text = self.tracer.replace("tval: 000000004883c057", "tval: 000000004883c557")
        self.assertNotEqual(text, self.tracer)
        with self.assertRaises(ValueError): c.tracer_exact(text, self.rows, self.symbols)

    def single_fixture(self):
        single = deepcopy(self.before); single["tests"] = [str(c.RUN / "code.vdb")]
        for metric, target in self.pre["targets"].items():
            row = single["metrics"][metric][target["scope"]]
            row["bits"] = hex(int(row["bits"], 16) | (1 << (row["width"] - 1 - target["point"]["raw_index"])))
        return single

    def test_targets_fixture(self):
        self.assertEqual(len(c.target_hits(self.before, self.single_fixture(), self.pre["targets"])), 2)

    def test_zero_gain_rejected(self):
        single = self.single_fixture(); t = self.pre["targets"]["branch"]
        single["metrics"]["branch"][t["scope"]]["bits"] = self.before["metrics"]["branch"][t["scope"]]["bits"]
        with self.assertRaises(ValueError): c.target_hits(self.before, single, self.pre["targets"])

    def test_shape_drift_rejected(self):
        single = self.single_fixture(); t = self.pre["targets"]["line"]
        single["metrics"]["line"][t["scope"]]["checksum"] = "0"
        with self.assertRaises(ValueError): c.target_hits(self.before, single, self.pre["targets"])

    def test_duplicate_vdb_rejected(self):
        before = deepcopy(self.before); before["tests"].append(str(c.RUN / "code.vdb"))
        with self.assertRaises(ValueError): c.target_hits(before, self.single_fixture(), self.pre["targets"])


if __name__ == "__main__":
    unittest.main()
