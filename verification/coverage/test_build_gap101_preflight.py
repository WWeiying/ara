import struct
import unittest
from types import SimpleNamespace
import build_gap101_preflight as m


def fixture():
    symbols = {s: 0x80000000 + i * 0x10000 for i, s in enumerate(m.SYMBOLS)}
    writes = {symbols[s] + off: value for (s, off), value in m.expected_words().items()}
    writes.update({symbols["tohost"]: 1, symbols["g75_result"]: m.CHECKS,
                   symbols["g75_result"] + 4: 0, symbols["num_failed"]: 0})
    writes.update({symbols["g101_restore"] + i * 8: 0 for i in range(4)})
    for phase in range(2):
        row = [2, symbols[("g101_bad_a", "g101_bad_b")[phase]], m.WORDS[phase], 1, 1-phase, 0, 0, phase+1]
        writes.update({symbols["g101_ledger"] + phase * 80 + i * 8: v for i, v in enumerate(row)})
    commits = [SimpleNamespace(pc=1, memory_accesses=tuple(writes.items()), vector_writes={})]
    for phase in range(2):
        for reg in range(32):
            commits.append(SimpleNamespace(pc=2, memory_accesses=(),
                vector_writes={reg: int.from_bytes(bytes([0x40 + reg]) * 128, "little")}))
    trace = "".join("exception trap_illegal_instruction, epc 0x%x\n" % symbols[s]
                    for s in ("g101_bad_a", "g101_bad_b"))
    return commits, symbols, trace


class Gap101Tests(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(m.validate(*fixture())["illegal_traps"], 2)

    def test_changed_vrf_not_skipped(self):
        c, s, t = fixture()
        writes = dict(c[0].memory_accesses)
        writes[s["g101_dump"] + 4096 + 4088] ^= 1
        c[0].memory_accesses = tuple(writes.items())
        with self.assertRaisesRegex(ValueError, "observed-byte"): m.validate(c, s, t)

    def test_missing_byte_evidence_rejected(self):
        c, s, t = fixture()
        c[0].memory_accesses = tuple((a, v) for a, v in c[0].memory_accesses if a != s["g101_target_dump"])
        with self.assertRaisesRegex(ValueError, "observed-byte"): m.validate(c, s, t)

    def test_target_changed_rejected(self):
        c, s, t = fixture()
        c[0].memory_accesses += ((s["g101_target_dump"] + 16, 0),)
        with self.assertRaisesRegex(ValueError, "observed-byte"): m.validate(c, s, t)

    def test_extra_trap_rejected(self):
        c, s, t = fixture()
        with self.assertRaisesRegex(ValueError, "two illegal"): m.validate(c, s, t + t)

    def test_rejected_word_retirement_rejected(self):
        c, s, t = fixture()
        c.append(SimpleNamespace(pc=s["g101_bad_a"], memory_accesses=(), vector_writes={}))
        with self.assertRaisesRegex(ValueError, "Rejected word"): m.validate(c, s, t)

    def test_extra_vector_write_rejected(self):
        c, s, t = fixture()
        c.append(SimpleNamespace(pc=3, memory_accesses=(), vector_writes={31: 0}))
        with self.assertRaisesRegex(ValueError, "VRF write"): m.validate(c, s, t)

    def test_ledger_policy_rejected(self):
        c, s, t = fixture()
        c[0].memory_accesses += ((s["g101_ledger"] + 24, 0),)
        with self.assertRaisesRegex(ValueError, "ledger"): m.validate(c, s, t)

    def test_opcode_fields(self):
        self.assertEqual(m.WORDS, (0xe2050827, 0x22050fa7))
        for phase, word in enumerate(m.WORDS):
            self.assertEqual(word & 127, 0x27)
            self.assertEqual((word >> 15) & 31, 10)
            self.assertEqual((word >> 7) & 31, (16, 31)[phase])

    def test_restore_rejected(self):
        c, s, t = fixture()
        c[0].memory_accesses += ((s["g101_restore"] + 8, 1),)
        with self.assertRaisesRegex(ValueError, "restoration"): m.validate(c, s, t)


if __name__ == "__main__": unittest.main()
