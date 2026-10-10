import unittest
from upstream_20261009_run import audit, baseline_gate, cases, expected


class OracleTests(unittest.TestCase):
    def fixture(self, suite):
        rows = cases(suite)
        trace = "".join(f"{i} {key} {value:016x}\n" for i, row in enumerate(rows)
                        for key, value in expected(suite, row).items())
        return rows, trace, f"UPSTREAM_COMPLETE cases={len(rows)}\n$finish called\n"

    def test_all_plans(self):
        for suite, count in (("load", 32), ("csr", 24), ("mmu", 192), ("ptw", 192)):
            rows, trace, log = self.fixture(suite)
            self.assertEqual(len(rows), count)
            self.assertEqual(audit(trace, log, suite, rows)["status"], "PASS")

    def test_missing_duplicate_unknown(self):
        rows, trace, log = self.fixture("load")
        for wrong in ("", trace.split("\n", 1)[1], trace + trace.splitlines()[0] + "\n",
                      trace.replace("0000000000000001", "xxxxxxxxxxxxxxxx", 1)):
            with self.assertRaises(ValueError):
                audit(wrong, log, "load", rows)

    def test_terminal_guards(self):
        rows, trace, log = self.fixture("mmu")
        for wrong in ("", log + log, log.replace("192", "191"), log + "Fatal: test"):
            with self.assertRaises(ValueError):
                audit(trace, wrong, "mmu", rows)

    def test_independent_failure_detection(self):
        for suite in ("load", "csr", "mmu", "ptw"):
            rows, trace, log = self.fixture(suite)
            first, rest = trace.split("\n", 1)
            i, key, value = first.split()
            wrong = f"{i} {key} {int(value, 16)^1:016x}\n" + rest
            self.assertEqual(len(audit(wrong, log, suite, rows)["failures"]), 1)

    def test_csr_mprv(self):
        self.assertEqual(expected("csr", (0, 3, 1, 0, 0))["after_mprv"], 1)
        for dest in (0, 1):
            self.assertEqual(expected("csr", (0, dest, 1, 0, 0))["after_mprv"], 0)
            self.assertEqual(expected("csr", (1, dest, 1, 0, 0))["after_mprv"], 0)

    def test_canonical_cause_tval_ownership(self):
        e = expected("mmu", (1, 1, 1, 0, 1, 0, 0))
        self.assertEqual(e["a_cause"], 15)
        self.assertEqual(e["a_tval"], 0x12345088 ^ (1 << 39))
        self.assertEqual(e["b_exception"], 0)
        e = expected("mmu", (0, 1, 1, 1, 1, 0, 0))
        self.assertEqual(e["a_exception"], 0)
        self.assertEqual(e["b_cause"], 13)

    def test_ptw_adjacent_dirty(self):
        for kind in range(3):
            self.assertEqual(expected("ptw", (kind, -1, 0, 2, 2, 0))["faults"], int(kind == 2))
        for bit in (1, 2, 4):
            self.assertEqual(expected("ptw", (0, 0, bit, 2, 0, 0))["requests"], 1)

    def test_baseline_must_not_accept_unrelated_failure_or_pass(self):
        for suite in ("load", "csr", "mmu", "ptw"):
            for failures in ([], [dict(id=0, field="unrelated", got=1, expected=0)]):
                with self.assertRaises(ValueError):
                    baseline_gate(dict(failures=failures), suite, cases(suite))


if __name__ == "__main__":
    unittest.main()
