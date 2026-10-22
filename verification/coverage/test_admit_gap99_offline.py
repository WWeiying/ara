import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import admit_gap99_offline as m


def row(insn=0x13, **kw):
    r = {field: 0 for field in m.common.COMMIT_FIELDS}
    r.update(event="retire", insn=insn, pc=0x80002000)
    r.update(kw)
    return r


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.runner.PRE / "preflight-manifest.json").read_bytes())
        self.meta = dict(entry=0x80000000, symbols=self.pre["symbols"])
        self.initial = 0x8000000000006600
        self.rows = []
        def read(csr, value):
            self.rows.append(row((csr << 20) | (2 << 12) | (5 << 7) | 0x73, rd=5, rd_wdata=value))
        def write(csr, value, rd=0):
            self.rows.append(row(rd=10, rd_wdata=value))
            self.rows.append(row((csr << 20) | (10 << 15) | (1 << 12) | (rd << 7) | 0x73, rd=rd))
        read(0x300, self.initial)
        read(0x180, 0)
        for phase, priv in enumerate((0, 0x800)):
            write(0x180, (1 << 60) | (0x12345 + phase), 6)
            read(0x180, 0)
            setting = (self.initial & ~0x21888) | 0x20000 | priv
            write(0x300, setting)
            read(0x300, setting)
            write(0x300, self.initial)
            read(0x300, self.initial)
        read(0x180, 0)
        s = self.meta["symbols"]
        stores = [(s["g99_observed"] + 8 * i, value, 8) for i, value in enumerate(m.oracle.expected_observations(0))]
        stores += [(s["g75_result"], 14, 4), (s["g75_result"] + 4, 0, 4), (s["num_failed"], 0, 4)]
        stores += [(s["g75_trap"] + off, 0, 8) for off in (0, 8, 16)]
        stores += [(s["tohost"], 1, 8)]
        for address, value, size in stores:
            self.rows.append(row(mem_addr=address, mem_wdata=value, mem_wmask=((1 << size) - 1) << (address & 7)))
        for i, r in enumerate(self.rows):
            r.update(order=i, cycle=i)

    def test_exact_architecture(self):
        result = m.architecture(self.rows, self.meta)
        self.assertEqual(result["exact_observed_bytes"], 96)
        self.assertEqual(result["checks"], 14)

    def test_wrong_observation(self):
        next(r for r in self.rows if r["mem_addr"] == self.meta["symbols"]["g99_observed"])["mem_wdata"] = 1
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_unproven_mode_input(self):
        self.rows[2]["rd_wdata"] = 9 << 60
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_missing_retirement(self):
        with self.assertRaises(ValueError):
            m.architecture(self.rows[1:], self.meta)

    def test_partial_terminal(self):
        self.rows[-1]["mem_wmask"] = 15
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_failed_signature(self):
        next(r for r in self.rows if r["mem_addr"] == self.meta["symbols"]["g75_result"])["mem_wdata"] = 13
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_actual_elf(self):
        self.assertEqual(m.elf_metadata(Path(self.pre["input_elf"]).read_bytes(), self.pre["symbols"]), self.meta)

    def test_wrong_observation_symbol(self):
        with self.assertRaises(ValueError):
            m.elf_metadata(Path(self.pre["input_elf"]).read_bytes(), dict(self.pre["symbols"], g99_observed=0))

    def test_no_cvX_activity_allowed(self):
        with patch.object(m.shape, "commit_rows", return_value=[row(event="cvx_req")]), self.assertRaises(ValueError):
            m.commit_rows(Path("ignored"))

    def test_no_arch_vector_allowed(self):
        with patch.object(m.shape, "commit_rows", return_value=[row(insn=0x82821857)]), self.assertRaises(ValueError):
            m.commit_rows(Path("ignored"))

    def test_vector_config_only(self):
        config = {k: "0" for k in m.common.VECTOR_FIELDS}
        config.update(event="config", nr_lanes="4", vlen_bits="1024")
        with patch.object(m.common, "read_csv", return_value=[config]):
            m.vector_zero(Path("ignored"))
        with patch.object(m.common, "read_csv", return_value=[config, dict(config, event="alloc")]), self.assertRaises(ValueError):
            m.vector_zero(Path("ignored"))

    def zero_log(self):
        return ("Core Test *** SUCCESS ***\n[ARA_CONTRACT] requests=0 responses=0 exceptions=0 "
                "mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n")

    def test_exact_zero_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(self.zero_log())
            self.assertEqual(m.zero_contract(path)["counts"]["requests"], 0)

    def test_zero_does_not_mask_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            for extra in ("Fatal: real failure\n", "[ARA_CONTRACT_ERROR] bad\n", "UVM_ERROR : 1\n",
                          "Core Test *** FAILED ***\n", self.zero_log()):
                path.write_text(self.zero_log() + extra)
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    m.zero_contract(path)

    def test_nonzero_contract_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(self.zero_log().replace("requests=0", "requests=1"))
            with self.assertRaises(ValueError):
                m.zero_contract(path)

    def test_vector_unobservable_not_fake_pass(self):
        vector = dict(status="UNOBSERVABLE", nr_lanes=4, vlen_bits=1024,
                      vector_destination_requests=0, prefix_vector_destination_requests=0, compared_instructions=0,
                      compared_bytes=0, skipped_unknown_bytes=0, non_bit_exact_instructions=0, unobservable_instructions=0,
                      incomplete_requests=[], unretired_requests=[], trapped_requests=[], instructions=[],
                      first_mismatch=None, stopped_at_spike_index=None)
        m.common.validate_vector(vector)
        vector["status"] = "PASS"
        with self.assertRaises(ValueError):
            m.common.validate_vector(vector)

    def test_scalar_prefix_rejected(self):
        result = dict(status="PREFIX", ara_trap_events=0, matched_instructions=1, ara_committed_instructions=1,
                      ara_retired_instructions=1, skipped_unobservable_register_values=0,
                      stopped_at_unobservable=None, mismatch=None)
        with self.assertRaises(ValueError):
            m.common.validate_scalar(result, 1)


if __name__ == "__main__":
    unittest.main()
