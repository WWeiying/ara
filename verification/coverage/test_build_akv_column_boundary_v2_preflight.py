import copy
import struct
from types import SimpleNamespace
import unittest

import build_akv_column_boundary_v2_preflight as b


def fixture():
    names = ("tohost", "g75_result", "num_failed", "g75_trap", "trap_fail", "boundary_status",
             "boundary_snapshots", "boundary_csrs", "boundary_scan")
    symbols = {n: 0x80010000+i*0x8000 for i, n in enumerate(names)}
    payloads = dict(tohost=struct.pack("<Q", 1), g75_result=struct.pack("<2I", 8422, 0),
        num_failed=struct.pack("<2I", 0, 0), g75_trap=bytes(24),
        boundary_status=struct.pack("<8I", 0,0,7,0,0,0,0,0),
        boundary_snapshots=struct.pack("<8192H", *b.expected_snapshots()),
        boundary_csrs=struct.pack("<24Q", *([21,0,64,8,2,1]*4)),
        boundary_scan=struct.pack("<8I", *([2048,0]*4)))
    commits = []
    for name, data in payloads.items():
        for i in range(0, len(data), 8):
            commits.append(SimpleNamespace(pc=0x80002000, instruction=0x3023,
                vector_writes={}, memory_accesses=[(symbols[name]+i, int.from_bytes(data[i:i+8], "little"))]))
    return commits, symbols


class SuccessorTest(unittest.TestCase):
    def test_complete_actual_observation_positive(self):
        commits, symbols = fixture()
        result = b.validate(commits, symbols)
        self.assertEqual(result["native_expected_custom_write_bytes"], 388)
        self.assertEqual(result["complete_snapshot_comparisons"], 8192)
        self.assertFalse(result["custom_instructions_executed"])
        self.assertEqual(result["actual_Spike_CSR_snapshot_bytes"], 192)

    def change(self, name, value, offset=0):
        commits, symbols = fixture()
        address = symbols[name]+offset
        target = next(c for c in commits if c.memory_accesses[0][0] == address)
        target.memory_accesses[0] = (address, value)
        with self.assertRaises(ValueError): b.validate(commits, symbols)

    def test_reject_zeroed_inactive_tail(self):
        self.change("boundary_snapshots", 0x343f, 8*128)

    def test_precise_inactive_seed(self):
        values = b.expected_snapshots()
        for phase in range(4):
            start = phase*2048+8*64
            self.assertEqual(values[start], 0x343f)
            self.assertEqual(values[start+1:start+64], list(range(0x1201, 0x1240)))

    def test_reject_fflags_difference(self): self.change("boundary_csrs", 0)
    def test_reject_vstart_difference(self): self.change("boundary_csrs", 1, 8)
    def test_reject_VL_difference(self): self.change("boundary_csrs", 63, 16)
    def test_reject_vtype_difference(self): self.change("boundary_csrs", 9, 24)
    def test_reject_vxrm_difference(self): self.change("boundary_csrs", 3, 32)
    def test_reject_vxsat_difference(self): self.change("boundary_csrs", 0, 40)
    def test_reject_partial_snapshot_scan(self): self.change("boundary_scan", 2047)
    def test_reject_snapshot_error(self): self.change("boundary_scan", (1<<32)|2048)
    def test_reject_missing_recovery(self): self.change("boundary_status", (1<<32), 8)
    def test_reject_failure_signature(self): self.change("g75_result", (1<<32)|8422)
    def test_reject_real_spike_trap(self): self.change("g75_trap", 2)

    def test_same_custom_workload(self):
        app = b.APP.read_text()
        for word in ("0x00b5605b", "0x0005745b", "0x0005355b", "0x0005365b", "0x0005375b", "0x0000505b"):
            self.assertIn(word, app)
        self.assertIn("i < active", app)
        self.assertNotIn("zero-filled inactive", app)
        self.assertIn("errors += boundary_snapshots[p][r][i] != expected_vrf[r][i]", app)
        self.assertLess(app.index("capture_csrs(0)"), app.index("snapshot(0)"))


if __name__ == "__main__":
    unittest.main()
