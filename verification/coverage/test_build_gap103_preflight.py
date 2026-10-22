"""Canonical oracle and negative trace fixtures, no DUT execution."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

import build_gap103_preflight as m


def fixtures():
    symbols = {name:0x90000000+i*0x10000 for i,name in enumerate(m.SYMBOLS)}
    def item(pc,insn=0x13,vector=None,**kw):
        return SimpleNamespace(pc=pc,instruction=insn,vector_writes=vector or {},memory_accesses=(),
            vector_sew=kw.get("sew"),vector_lmul=kw.get("lmul"),vector_vl=kw.get("vl"),
            vector_vstart=kw.get("start"),vector_tail_agnostic=False,vector_mask_agnostic=False)
    commits = [item(0x80000000+r*4,0x5e02c057|(r<<7),
                    {r:int.from_bytes(bytes([0x40+r])*128,"little")}) for r in range(32)]
    data = m.images()
    for name,word,regs,image,sew,lmul,vl,start in (
            ("g103_load_seed",0x02066407,range(8,16),data["seeded"],32,"m8",256,0),
            ("g103_load_shift",0x02065607,range(12,16),data["before"],16,"m4",256,0),
            ("g103_narrow",m.WORD,range(8,11),data["after"],16,"m4",129,13)):
        commits.append(item(symbols[name],word,{r:int.from_bytes(image[r*128:(r+1)*128],"little") for r in regs},
                            sew=sew,lmul=lmul,vl=vl,start=start))
    commits.append(item(symbols["g103_recovery"],0x02005427,sew=16,lmul="m1",vl=1,start=0))
    scalar = item(0x80001008)
    words = {(symbols[n]+offset):value for (n,offset),value in m.expected_words().items()}
    words.update({symbols["g75_trap"]+i*8:0 for i in range(3)})
    words.update({symbols["g75_result"]:m.CHECKS,symbols["g75_result"]+4:0,
                  symbols["num_failed"]:0,symbols["tohost"]:1})
    scalar.memory_accesses = tuple(words.items()); commits.append(scalar)
    return symbols,commits


class PreflightTests(unittest.TestCase):
    def test_opcode_independent_fields(self):
        self.assertEqual(m.WORD,0xb2860457)
        self.assertEqual(((m.WORD>>26),(m.WORD>>25)&1,(m.WORD>>20)&31,
                          (m.WORD>>15)&31,(m.WORD>>12)&7,(m.WORD>>7)&31),(44,1,8,12,0,8))

    def test_canonical_alias_not_original_seed(self):
        data = m.images(); before = data["before"]
        self.assertEqual(before[1536:2048],data["shifts"][16:-16])
        self.assertNotEqual(before[1536:1540],data["seeded"][1536:1540])
        for i in range(13,129):
            wide = int.from_bytes(before[1024+4*i:1028+4*i],"little")
            shift = int.from_bytes(before[1536+2*i:1538+2*i],"little")
            self.assertEqual(int.from_bytes(data["after"][1024+2*i:1026+2*i],"little"),
                             (wide >> (shift%32))%65536)

    def test_full_prestart_tail_other_registers(self):
        data=m.images()
        self.assertEqual(data["before"][:1050],data["after"][:1050])
        self.assertEqual(data["before"][1282:],data["after"][1282:])
        self.assertEqual(len(m.expected_words())+3,m.CHECKS)

    def test_exact_positive_trace(self):
        symbols,commits=fixtures()
        self.assertEqual(m.validate(commits,symbols,"")["checks"],1245)

    def test_all_region_corruption_rejected(self):
        symbols,commits=fixtures()
        for name,offset in (("g103_before_dump",1056),("g103_after_dump",1056),
                ("g103_after_dump",0),("g103_after_dump",4088),("g103_seed_dump",0),
                ("g103_shift_dump",536),("g103_csr",16),("g103_csr",56),
                ("g103_recovery_dump",16),("g75_trap",0)):
            bad=deepcopy(commits); address=symbols[name]+offset
            bad[-1].memory_accesses=tuple((a,v^1 if a==address else v) for a,v in bad[-1].memory_accesses)
            with self.subTest(name=name,offset=offset),self.assertRaises(ValueError): m.validate(bad,symbols,"")

    def test_narrow_policy_opcode_vstart_rejected(self):
        symbols,commits=fixtures()
        for key,value in (("instruction",m.WORD^0x80),("vector_vstart",0),("vector_vl",128),
                          ("vector_tail_agnostic",True),("vector_mask_agnostic",True)):
            bad=deepcopy(commits); setattr(bad[34],key,value)
            with self.subTest(key=key),self.assertRaises(ValueError): m.validate(bad,symbols,"")

    def test_missing_extra_vector_bytes_rejected(self):
        symbols,commits=fixtures()
        for reg in (8,9,10):
            bad=deepcopy(commits); bad[34].vector_writes[reg]^=1
            with self.assertRaises(ValueError): m.validate(bad,symbols,"")
        bad=deepcopy(commits); bad[34].vector_writes[12]=0
        with self.assertRaises(ValueError): m.validate(bad,symbols,"")

    def test_missing_observation_and_trap_rejected(self):
        symbols,commits=fixtures(); bad=deepcopy(commits)
        bad[-1].memory_accesses=bad[-1].memory_accesses[1:]
        with self.assertRaises(ValueError): m.validate(bad,symbols,"")
        with self.assertRaises(ValueError): m.validate(commits,symbols,"exception trap_illegal_instruction")


if __name__ == "__main__": unittest.main()
