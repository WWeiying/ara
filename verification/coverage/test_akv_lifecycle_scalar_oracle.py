import json
import unittest

import akv_lifecycle_scalar_oracle as oracle


class ScalarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = (oracle.runner.PRE/"input.elf").read_bytes()
        cls.symbols = json.loads((oracle.runner.PRE/"preflight-manifest.json").read_text())["symbols"]

    def model(self):
        return oracle.Model(self.blob, self.symbols)

    def instruction(self, word, a=0, b=0):
        m = self.model()
        m.memory.update({m.pc+i:v for i,v in enumerate(word.to_bytes(4,"little"))})
        m.gpr[1], m.gpr[2] = a, b
        return m, m.step()

    def test_actual_sealed_ELF_independent_terminal(self):
        m, result = oracle.replay(self.blob, self.symbols)
        self.assertEqual(m.steps, 154773)
        self.assertEqual(result["instruction_counts"]["mret"], 4)
        self.assertFalse(result["full_scalar_independent_qualified"])

    def test_complete_synthetic_retirement_replay(self):
        # Synthetic unit-test stream, not actual DUT qualification.
        m=self.model();rows=[]
        while not m.terminal:
            e=m.step()
            if e["trap"]:continue
            rows.append(dict(e,event="retire",order=len(rows),mem_wdata=e.get("store_value",0)))
        _,result=oracle.replay(self.blob,self.symbols,rows)
        self.assertEqual(result["matched_retirements"],154769)
        self.assertTrue(result["full_scalar_independent_qualified"])

    def test_terminal_failure_not_returncode(self):
        m=self.model()
        word=(2<<20)|(1<<15)|(3<<12)|0x23
        m.memory.update({m.pc+i:v for i,v in enumerate(word.to_bytes(4,"little"))})
        m.gpr[1]=self.symbols["tohost"];m.gpr[2]=3
        with self.assertRaises(ValueError):m.step()

    def test_wrong_ELF_rejected(self):
        with self.assertRaises(ValueError): oracle.Model(self.blob+b"x",self.symbols)

    def test_partial_trace_rejected(self):
        with self.assertRaises(ValueError): oracle.replay(self.blob,self.symbols,[])

    def test_unknown_instruction(self):
        with self.assertRaises(ValueError): self.instruction(0xffffffff)

    def test_addiw_sign_extension(self):
        _, e = self.instruction(0x0000819b, 0x80000000)
        self.assertEqual(e["rd_wdata"],0xffffffff80000000)

    def test_srl(self):
        _, e = self.instruction((2<<20)|(1<<15)|(5<<12)|(3<<7)|0x33,1<<63,63)
        self.assertEqual(e["rd_wdata"],1)

    def test_signed_branch(self):
        m,e = self.instruction((2<<8)|(2<<20)|(1<<15)|(4<<12)|0x63,oracle.MASK,0)
        self.assertEqual(m.pc,e["pc"]+4)

    def test_unaligned_branch_rejected(self):
        with self.assertRaises(ValueError):
            self.instruction((1<<8)|(2<<20)|(1<<15)|(4<<12)|0x63,oracle.MASK,0)

    def test_invalid_integer_encoding(self):
        with self.assertRaises(ValueError): self.instruction((0x20<<25)|(2<<12)|0x33)

    def test_wrong_mret(self):
        with self.assertRaises(ValueError): self.instruction(0x30200073)

    def test_uninitialized_load(self):
        with self.assertRaises(ValueError): self.instruction((1<<15)|(3<<12)|(3<<7)|3,0x801ff000)

    def test_wrong_scalar_GPR(self):
        _, e = self.instruction(0x00108193,7)
        observed = dict(e,rd_wdata=9)
        with self.assertRaises(ValueError): oracle.base.compare_retirement(e,observed,0)

    def test_wrong_scalar_store(self):
        expected = dict(pc=4,insn=0x23,rd=0,mem_addr=8,mem_rmask=0,mem_wmask=1,trap=0,
                        store_value=3,store_size=1)
        with self.assertRaises(ValueError):
            oracle.base.compare_retirement(expected,dict(expected,mem_wdata=4),0)

    def test_wrong_branch_PC(self):
        _, e = self.instruction(0x00108193,7)
        with self.assertRaises(ValueError): oracle.base.compare_retirement(e,dict(e,pc=e["pc"]+4),0)

    def test_wrong_trap(self):
        _, e = self.instruction(0x00108193,7)
        with self.assertRaises(ValueError): oracle.base.compare_retirement(e,dict(e,trap=1),0)

    def test_wrong_CSR(self):
        m=self.model()
        with self.assertRaises(ValueError): m.csr_write(0x304,1)

    def test_snapshot_order(self):
        m=self.model(); m.csr.update({0xc20:64,0xc21:8,8:0})
        with self.assertRaises(ValueError): m.vector(0x02005027)

    def test_custom_site_binding(self):
        m=self.model()
        with self.assertRaises(ValueError): m.custom(oracle.fixture.WORDS[0])

    def test_final_memory_region_overlap(self):
        s=dict(self.symbols,lifecycle_sources=self.symbols["lifecycle_seed"])
        with self.assertRaises(ValueError): oracle.expected_memory(s)


if __name__ == "__main__": unittest.main()
