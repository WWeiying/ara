import unittest
from types import SimpleNamespace
import build_gap101a_preflight as m


def fixture():
    s = {key: 0x80000000+i*0x10000 for i, key in enumerate(m.SYMBOLS)}
    w = {s[key]+offset: value for (key, offset), value in m.expected_words().items()}
    w.update({s["tohost"]:1, s["g75_result"]:539, s["g75_result"]+4:0, s["num_failed"]:0})
    row = [2, s["g101a_bad_a"], 0xe2050827, 1, 1, 0, 0, 1]
    w.update({s["g101a_ledger"]+i*8:v for i,v in enumerate(row)})
    w.update({s["g101a_restore"]+i*8:0 for i in range(4)})
    c = [SimpleNamespace(pc=1, memory_accesses=tuple(w.items()), vector_writes={})]
    c += [SimpleNamespace(pc=2, memory_accesses=(), vector_writes={r:int.from_bytes(bytes([0x40+r])*128,"little")})
          for r in range(32)]
    return c,s,"exception trap_illegal_instruction, epc 0x%x\n" % s["g101a_bad_a"]


class Tests(unittest.TestCase):
    def test_pass(self): self.assertEqual(m.validate(*fixture())["checks"],539)
    def test_changed_vrf(self):
        c,s,t=fixture();c[0].memory_accesses+=((s["g101a_dump"]+4088,0),)
        with self.assertRaisesRegex(ValueError,"Observed bytes"):m.validate(c,s,t)
    def test_missing_guard(self):
        c,s,t=fixture();c[0].memory_accesses=tuple((a,v) for a,v in c[0].memory_accesses if a!=s["g101a_target_dump"])
        with self.assertRaisesRegex(ValueError,"Observed bytes"):m.validate(c,s,t)
    def test_extra_trap(self):
        c,s,t=fixture()
        with self.assertRaises(ValueError):m.validate(c,s,t+t)
    def test_recovery_wrong(self):
        c,s,t=fixture();c[0].memory_accesses+=((s["g101a_recovery_dump"]+16,0),)
        with self.assertRaises(ValueError):m.validate(c,s,t)


if __name__ == "__main__": unittest.main()
