from dataclasses import replace
from pathlib import Path
import unittest

import build_gap102b_preflight as m
from ara_verify.spike_trace import SpikeCommit


def fixture():
    symbols={name:0x80000000+i*0x10000 for i,name in enumerate(m.SYMBOLS)}
    def commit(pc,vectors=None,instruction=0x13,memory=()):
        return SpikeCommit(pc,instruction,{},{},vectors or {},{},memory)
    data=m.images()
    rows=[commit(0x80000004,{r:int.from_bytes(bytes([0x40+r])*128,"little")}) for r in range(32)]
    for key,regs,stage,sew,lmul,vl,start in (("g102b_load_seed",range(8,16),"seeded",32,"m8",256,0),
            ("g102b_load_source",[14],"before",16,"m4",129,128),
            ("g102b_mac",[12],"after",16,"m4",129,128)):
        row=commit(symbols[key],{r:int.from_bytes(data[stage][r*128:(r+1)*128],"little") for r in regs},
                   instruction=m.WORD if key=="g102b_mac" else 0x13)
        rows.append(replace(row,vector_sew=sew,vector_lmul=lmul,vector_vl=vl,vector_vstart=start,
                            vector_tail_agnostic=False,vector_mask_agnostic=False))
    rows.append(replace(commit(symbols["g102b_recovery"],instruction=0x27|(12<<7)),
                        vector_sew=32,vector_lmul="m1",vector_vl=1,vector_vstart=0))
    memory=[(symbols[name]+offset,value) for (name,offset),value in m.expected_words().items()]
    memory += [(symbols["g75_trap"]+i*8,0) for i in range(3)]
    memory += [(symbols["g75_result"],723),(symbols["g75_result"]+4,0),(symbols["num_failed"],0),(symbols["tohost"],1)]
    rows.append(commit(0x80000008,memory=tuple(memory)))
    return rows,symbols,""


class PreflightTests(unittest.TestCase):
    def test_all_new_source_paths_exist(self):
        for path in (m.APP,Path(m.__file__).with_name("test_build_gap102b_preflight.py"),
                     m.ROOT/"verification/tests/gap102b_host_reference.c",
                     m.ROOT/"verification/tests/gap102b_reference.h"):
            self.assertTrue(path.is_file(),str(path))
    def test_exact_before_and_after_images(self):
        data=m.images()
        self.assertEqual([i for i,(a,b) in enumerate(zip(data["seeded"],data["before"])) if a!=b],[1792,1793])
        self.assertEqual(data["before"][1536:1540],(0x51004180).to_bytes(4,"little"))
        self.assertEqual(data["after"][1536:1540],(0x51013300).to_bytes(4,"little"))
        self.assertEqual(data["after"][:1536],data["before"][:1536])
        self.assertEqual(data["after"][1540:],data["before"][1540:])

    def test_full_contract(self):
        result=m.validate(*fixture())
        self.assertEqual((result["checks"],result["active_result_bytes"],result["vstart"]),(723,4,128))
        self.assertEqual(m.WORD,0xf2c56457)

    def test_zero_or_short_vstart_rejected(self):
        for vl,start in ((129,0),(128,128),(130,128),(129,127)):
            with self.assertRaises(ValueError):m.images(vl,start)

    def test_source_register_and_vstart_rejected(self):
        for field,value in (("vector_vstart",0),("vector_tail_agnostic",None),("vector_writes",{12:0})):
            rows,symbols,text=fixture();i=next(i for i,c in enumerate(rows) if c.pc==symbols["g102b_load_source"])
            rows[i]=replace(rows[i],**{field:value})
            with self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_mac_vstart_policy_and_extra_write_rejected(self):
        for field,value in (("vector_vstart",0),("vector_mask_agnostic",None),("vector_writes",{12:0,14:0})):
            rows,symbols,text=fixture();i=next(i for i,c in enumerate(rows) if c.pc==symbols["g102b_mac"])
            rows[i]=replace(rows[i],**{field:value})
            with self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_full_wide_seed_required(self):
        rows,symbols,text=fixture();i=next(i for i,c in enumerate(rows) if c.pc==symbols["g102b_load_seed"])
        writes=dict(rows[i].vector_writes);writes.pop(12);rows[i]=replace(rows[i],vector_writes=writes)
        with self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_full_guards_csr_and_tail(self):
        for name,offset in (("g102b_dump",1536),("g102b_dump",1528),("g102b_dump",4088),
                            ("g102b_source_dump",504),("g102b_seed_dump",0),
                            ("g102b_csr",16),("g102b_csr",48),("g102b_recovery_dump",16)):
            rows,symbols,text=fixture();memory=list(rows[-1].memory_accesses)
            i=next(i for i,(a,v) in enumerate(memory) if a==symbols[name]+offset)
            a,v=memory[i];memory[i]=(a,v^1);rows[-1]=replace(rows[-1],memory_accesses=tuple(memory))
            with self.subTest(name=name,offset=offset),self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_trap_and_implicit_vector_side_effect(self):
        rows,symbols,text=fixture()
        with self.assertRaises(ValueError):m.validate(rows,symbols,"exception illegal")
        rows.insert(0,SpikeCommit(0x80002000,0x13,{},{},{8:0},{},()))
        with self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_frozen_source_special_gates(self):
        text=(m.OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv").read_text()
        self.assertFalse(m.gate_audit(text)["source_snapshot_expected"])
        bad=text.replace("active_register_mask(lmul, target_eew, vstart, vl)","active_register_mask(lmul, target_eew, 0, vl)")
        with self.assertRaises(ValueError):m.gate_audit(bad)

    def test_source_program_reloads_vstart_before_mac(self):
        text=m.APP.read_text()
        self.assertEqual(text.count('"li t0, 128\\ncsrw vstart, t0\\n"'),2)
        self.assertIn("vse32.v v12,",text)
        self.assertNotIn("vse32.v v8,",text)


if __name__=="__main__":unittest.main()
