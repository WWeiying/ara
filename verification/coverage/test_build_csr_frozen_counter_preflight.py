import copy
from types import SimpleNamespace
import unittest

import build_csr_frozen_counter_preflight as p


def csr(addr, funct, rd=0, rs=0, writes=None):
    return SimpleNamespace(instruction=addr << 20 | rs << 15 | funct << 12 | rd << 7 | 0x73,
                           pc=0, vector_writes={}, gpr_writes=writes or {}, memory_accesses=[])


def fixture():
    symbols = dict(tohost=0x1000, g75_result=0x2000, num_failed=0x3000, g75_trap=0x4000,
                   trap_fail=0x5000, counter_observed=0x6000, counter_guards=0x7000)
    rows = [csr(0x320, 1, rs=1)]
    rows[0].gpr_writes = {}
    # A preceding scalar instruction supplies independent register constants.
    rows.insert(0, SimpleNamespace(instruction=0x13, pc=0, vector_writes={},
                 gpr_writes={1: 5, 2: p.SEED, 3: 0}, memory_accesses=[]))
    for addr in (0xb00, 0xb02):
        for _ in range(8):
            rows += [csr(addr, 1, rs=2), csr(addr, 1, rd=4, rs=2),
                     csr(addr, 2, rd=4), csr(addr + 0x100, 2, rd=4)]
        rows += [csr(addr, 1)]
    rows += [csr(0x320, 1)]
    rows[-1].memory_accesses = [(symbols["counter_observed"] + 8 * i, v) for i, v in enumerate(p.expected())]
    rows[-1].memory_accesses += [(0x1000, 1), (0x2000, 54), (0x2004, 0), (0x3000, 0),
                                 (0x4000, 0), (0x4008, 0), (0x4010, 0)]
    return rows, symbols


class CounterPreflightTests(unittest.TestCase):
    def test_independent_gold(self):
        gold = p.expected()
        self.assertEqual(len(gold), 52)
        self.assertEqual(gold[:6], [5, 5, 5, p.SEED, 0xfedcba9876543210, 0xfedcba9876543210])
        self.assertEqual(gold[3:27], gold[27:51])

    def test_positive(self):
        rows, symbols = fixture()
        self.assertEqual(p.validate(rows, symbols)["checks"], 54)

    def reject(self, modify):
        rows, symbols = fixture()
        modify(rows, symbols)
        with self.assertRaises(ValueError):
            p.validate(rows, symbols)

    def test_wrong_counter_value(self):
        self.reject(lambda rows, s: rows[-1].memory_accesses.__setitem__(3, (s["counter_observed"] + 24, 0)))

    def test_running_counter_rejected(self):
        self.reject(lambda rows, s: rows[0].gpr_writes.__setitem__(1, 0))

    def test_unprimed_read(self):
        self.reject(lambda rows, s: rows.pop(2))

    def test_missing_cell(self):
        self.reject(lambda rows, s: rows.pop(3))

    def test_alias_write(self):
        self.reject(lambda rows, s: setattr(rows[5], "instruction", csr(0xc00, 1, rd=4, rs=2).instruction))

    def test_trap_rejected(self):
        self.reject(lambda rows, s: setattr(rows[4], "pc", s["trap_fail"]))

    def test_vector_rejected(self):
        self.reject(lambda rows, s: setattr(rows[4], "vector_writes", {1: 2}))

    def test_duplicate_terminal(self):
        self.reject(lambda rows, s: rows[-1].memory_accesses.append((s["tohost"], 1)))

    def test_guard_write(self):
        self.reject(lambda rows, s: rows[-1].memory_accesses.append((s["counter_guards"], p.GUARDS[0])))

    def test_real_frozen738_shape(self):
        pins = {}
        evidence = p.target_evidence(pins)
        self.assertEqual({r["raw_index"] for r in evidence["targets"] if r["metric"] == "cond"}, {90, 92})
        self.assertTrue(all(not r["hit"] for r in evidence["targets"]))
        self.assertEqual(pins[str(p.inventory.SOURCE)],
                         "635466f3c536e290b6cdf208c12cef762ed394fbf701e03c89ecf770420d12f4")


if __name__ == "__main__":
    unittest.main()
