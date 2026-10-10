from dataclasses import replace
import unittest
import build_gap102_preflight as m
from ara_verify.spike_trace import SpikeCommit


def fixture():
    symbols = {name:0x80000000 + i*0x10000 for i,name in enumerate(m.SYMBOLS)}
    def commit(pc, vectors=None, instruction=0x13, memory=()):
        return SpikeCommit(pc, instruction, {}, {}, vectors or {}, {}, memory)
    data = m.images()
    commits = [commit(0x80000004, {r:int.from_bytes(bytes([0x40+r])*128,"little")}) for r in range(32)]
    for key, regs, stage in [("g102_load_seed",range(8,16),"seeded"),
                             ("g102_load_source",range(12,16),"before"), ("g102_mac",range(8,16),"after")]:
        row = commit(symbols[key], {r:int.from_bytes(data[stage][r*128:(r+1)*128],"little") for r in regs})
        if key == "g102_mac":
            row = replace(row,instruction=m.WORD,vector_sew=16,vector_lmul="m4",vector_vl=129,
                          vector_vstart=0,vector_tail_agnostic=False,vector_mask_agnostic=False)
        commits.append(row)
    commits.append(commit(symbols["g102_recovery"]))
    memory = [(symbols[name]+offset,value) for (name,offset),value in m.expected_words().items()]
    memory += [(symbols["g75_trap"]+i*8,0) for i in range(3)]
    memory += [(symbols["g75_result"],m.CHECKS),(symbols["g75_result"]+4,0),
               (symbols["num_failed"],0),(symbols["tohost"],1)]
    commits.append(commit(0x80000008,memory=tuple(memory)))
    return commits,symbols,""


class PreflightTests(unittest.TestCase):
    def test_opcode_fields(self):
        self.assertEqual(m.WORD,0xf2c56457)
        self.assertEqual(((m.WORD>>7)&31,(m.WORD>>15)&31,(m.WORD>>20)&31),(8,10,12))

    def test_crossed_source_accumulator_alias(self):
        data=m.images()
        self.assertEqual(int.from_bytes(data["before"][1536:1540],"little"),0x10251000)
        self.assertEqual(int.from_bytes(data["after"][1536:1540],"little"),0x10260180)
        self.assertEqual(data["after"][1540:],data["before"][1540:])

    def test_short_vl_not_target(self):
        with self.assertRaisesRegex(ValueError,"crossed"):
            m.images(79)

    def test_full_oracle(self):
        self.assertEqual(m.validate(*fixture())["checks"],723)

    def test_tail_change_rejected(self):
        rows,symbols,text=fixture()
        memory=list(rows[-1].memory_accesses)
        index=next(i for i,(a,v) in enumerate(memory) if a==symbols["g102_dump"]+1544)
        address,value=memory[index];memory[index]=(address,value^1)
        rows[-1]=replace(rows[-1],memory_accesses=tuple(memory))
        with self.assertRaisesRegex(ValueError,"oracle differs"):
            m.validate(rows,symbols,text)

    def test_unknown_policy_rejected(self):
        rows,symbols,text=fixture()
        i=next(i for i,r in enumerate(rows) if r.pc==symbols["g102_mac"])
        rows[i]=replace(rows[i],vector_tail_agnostic=None)
        with self.assertRaisesRegex(ValueError,"policy"):
            m.validate(rows,symbols,text)

    def test_unexpected_trap_rejected(self):
        rows,symbols,_=fixture()
        with self.assertRaisesRegex(ValueError,"trap"):
            m.validate(rows,symbols,"exception trap_illegal_instruction")


if __name__ == "__main__":
    unittest.main()
