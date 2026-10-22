"""Extra granted-byte negative fixtures; frozen v3 sources stay unchanged."""
from copy import deepcopy
import csv
import unittest

import collect_gap102b_strict_v3 as c


class GrantedByteTests(unittest.TestCase):
    def rows(self):
        with (c.RUN / "vector_trace.csv").open() as handle:
            return list(csv.DictReader(handle))

    def corrupt_stage(self, opcode, vd, vstart):
        rows = self.rows()
        indices = [i for i, row in enumerate(rows) if row["event"] == "write" and
                   row["insn"] == opcode and row["vd"] == vd and
                   row["vstart"] == vstart and int(row["be"], 16)]
        self.assertTrue(indices)
        for i in indices:
            be = int(rows[i]["be"], 16)
            for byte in range(8):
                if not be & (1 << byte):
                    continue
                changed = deepcopy(rows)
                changed[i]["wdata"] = "%016x" % (int(rows[i]["wdata"], 16) ^ (1 << (8*byte)))
                with self.subTest(row=i, byte=byte), self.assertRaises(ValueError):
                    c.transport_exact(changed)
            missing = deepcopy(rows)
            missing[i]["be"] = "00"
            with self.assertRaises(ValueError):
                c.transport_exact(missing)

    def test_source_active_both_granted_bytes(self):
        self.corrupt_stage("0206d607", "12", "128")

    def test_mac_active_four_granted_bytes(self):
        self.corrupt_stage("f2c56457", "8", "128")

    def test_maintenance_all128_granted_bytes(self):
        self.corrupt_stage("f2c56457", "14", "0")


if __name__ == "__main__":
    unittest.main()
