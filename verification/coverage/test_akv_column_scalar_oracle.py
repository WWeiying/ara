import copy
from pathlib import Path
import struct
import unittest

import akv_column_scalar_oracle as o


def elf(words,data=b"",bss=256):
    code=b"".join(w.to_bytes(4,"little") for w in words)
    header=b"\x7fELF\x02\x01\x01"+bytes(9)+struct.pack("<HHIQQQIHHHHHH",2,243,1,0x80000000,64,0,0,64,56,2,64,0,0)
    ph=struct.pack("<IIQQQQQQ",1,5,176,0x80000000,0x80000000,len(code),len(code),4)
    ph+=struct.pack("<IIQQQQQQ",1,6,176+len(code),0x80001000,0x80001000,len(data),len(data)+bss,8)
    return header+ph+code+data


def model(words,data=b""):
    return o.Model(elf(words,data),dict(tohost=0x80001000,boundary_bad=0x80000004))


def imm(rd,rs,constant,f3=0):
    return ((constant&4095)<<20)|(rs<<15)|(f3<<12)|(rd<<7)|0x13


class InterpreterTest(unittest.TestCase):
    def test_reset_GPR_CSR_and_ELF_bss(self):
        m=model([imm(1,0,1)],b"\x12\x34")
        self.assertEqual(m.gpr,[0]*32)
        self.assertEqual(m.csr[0x300],0xa00000000)
        self.assertEqual(m.csr[0x305],0x80000040)
        self.assertEqual(m.read(0x80001000,4),b"\x12\x34\0\0")

    def test_signed_wrap_add_and_x0(self):
        m=model([imm(1,0,-1),imm(2,1,1),imm(0,1,5)])
        self.assertEqual(m.step()["rd_wdata"],o.MASK)
        self.assertEqual(m.step()["rd_wdata"],0)
        self.assertEqual(m.step()["rd"],0)
        self.assertEqual(m.gpr[0],0)

    def test_shift63_sign_bits(self):
        m=model([imm(1,0,1),imm(2,1,63,1)])
        m.step();self.assertEqual(m.step()["rd_wdata"],1<<63)

    def test_sltu_is_unsigned(self):
        word=(2<<20)|(1<<15)|(3<<12)|(3<<7)|0x33
        m=model([word]);m.gpr[1]=o.MASK;m.gpr[2]=1
        self.assertEqual(m.step()["rd_wdata"],0)

    def test_negative_lui(self):
        m=model([0xfffff0b7]);self.assertEqual(m.step()["rd_wdata"],0xfffffffffffff000)

    def test_auipc_independent_PC(self):
        m=model([0x00001097]);self.assertEqual(m.step()["rd_wdata"],0x80001000)

    def test_jalr_reads_old_rs1_when_rd_equal(self):
        m=model([0x000080e7,imm(2,0,0)])
        m.gpr[1]=0x80000005
        self.assertEqual(m.step()["rd_wdata"],0x80000004)
        self.assertEqual(m.pc,0x80000004)

    def test_branch_taken_and_not_taken(self):
        for value,expected in ((0,0x80000008),(1,0x80000004)):
            m=model([0x00008463,imm(2,0,0),imm(2,0,0)]);m.gpr[1]=value
            m.step();self.assertEqual(m.pc,expected)

    def test_jal_signed_negative_offset(self):
        m=model([imm(1,0,0),0xffdff06f]);m.step();m.step()
        self.assertEqual(m.pc,0x80000000)

    def test_signed_LH_and_unsigned_LHU(self):
        for f3,expected in ((1,o.MASK),(5,65535)):
            m=model([(1<<15)|(f3<<12)|(2<<7)|3],b"\xff\xff")
            m.gpr[1]=0x80001000
            self.assertEqual(m.step()["rd_wdata"],expected)

    def test_signed_LW(self):
        m=model([0x0000a103],b"\0\0\0\x80");m.gpr[1]=0x80001000
        self.assertEqual(m.step()["rd_wdata"],0xffffffff80000000)

    def test_store_address_byte_mask_and_truncation(self):
        m=model([0x00209123]);m.gpr[1]=0x80001000;m.gpr[2]=0x123456
        effect=m.step()
        self.assertEqual(effect["mem_wmask"],12)
        self.assertEqual(m.read(0x80001002,2),b"\x56\x34")

    def test_unknown_stack_read_rejected(self):
        m=model([0x0000b103]);m.gpr[1]=0x801fff00
        with self.assertRaisesRegex(ValueError,"Unknown/outside memory"):m.step()

    def test_misaligned_load_rejected(self):
        m=model([0x0000b103]);m.gpr[1]=0x80001001
        with self.assertRaisesRegex(ValueError,"Misaligned"):m.step()

    def test_unknown_instruction_rejected(self):
        for word in (0x00000000,0x02000033,0x40005013,0x0000003b,0x00000053):
            with self.subTest(word=hex(word)),self.assertRaises(ValueError):model([word]).step()

    def test_unknown_CSR_rejected(self):
        with self.assertRaisesRegex(ValueError,"Unsupported CSR"):model([0x340020f3]).step()

    def test_csr_result_and_independent_state(self):
        m=model([0x001ad073,0x001020f3]);m.step()
        self.assertEqual(m.step()["rd_wdata"],21)
        self.assertEqual(m.csr[1],21)

    def test_readonly_CSR_write_rejected(self):
        m=model([0xc20010f3])
        with self.assertRaisesRegex(ValueError,"read-only CSR"):m.step()

    def test_invalid_terminal_rejected(self):
        m=model([0x0020b023]);m.gpr[1]=0x80001000;m.gpr[2]=3
        with self.assertRaisesRegex(ValueError,"terminal oracle"):m.step()

    def test_output_comparison_does_not_update_model(self):
        m=model([imm(1,0,5)]);expected=m.step();state=list(m.gpr)
        observed=dict(expected,rd_wdata=6)
        with self.assertRaisesRegex(ValueError,"GPR result"):o.compare_retirement(expected,observed,0)
        self.assertEqual(m.gpr,state)

    def test_wrong_control_flow_PC_rejected(self):
        expected=dict(pc=4,insn=1,rd=0,mem_addr=0,mem_rmask=0,mem_wmask=0,trap=0)
        with self.assertRaisesRegex(ValueError,"pc mismatch"):
            o.compare_retirement(expected,dict(expected,pc=8),1)

    def test_wrong_store_data_rejected(self):
        expected=dict(pc=4,insn=1,rd=0,mem_addr=0x80001000,mem_rmask=0,mem_wmask=3,trap=0,store_size=2,store_value=0x1234)
        with self.assertRaisesRegex(ValueError,"store data"):
            o.compare_retirement(expected,dict(expected,mem_wdata=0x1235),1)

    def test_self_modifying_store_rejected(self):
        m=model([imm(1,0,1)])
        with self.assertRaisesRegex(ValueError,"self-modifying"):m.write(0x80000000,b"\0")

    def test_independent_column_error_and_precise_trap(self):
        m=model([o.native.WORDS[1],o.native.WORDS[2]])
        m.pc=0x80000004;m.csr.update({0xc20:64,0xc21:8,0x305:0x80000000})
        m.commands=[{},{}];m.context=dict(ready=True,head=64,tokens=1,rows=[bytes(128)]*3)
        m.gpr[10]=64
        effect=m.step()
        self.assertEqual(effect["trap"],1)
        self.assertEqual((m.csr[0x341],m.csr[0x342],m.csr[0x343]),(0x80000004,2,0))
        self.assertEqual(m.pc,0x80000000)
        self.assertEqual(m.commands[-1]["write_bytes"],0)

    def test_column_preserves_inactive_seed(self):
        m=model([o.native.WORDS[1]])
        m.commands=[{}];m.csr.update({0xc20:64,0xc21:8});m.gpr[10]=63
        m.vrf[8]=bytearray(range(128));old=bytes(m.vrf[8])
        m.context=dict(ready=True,head=64,tokens=1,rows=[bytes(128),bytes([7])*128,bytes(128)])
        m.step();self.assertEqual(m.vrf[8][:2],b"\7\7");self.assertEqual(m.vrf[8][2:],old[2:])


class ActualSealedReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=o.life.read_bound(o.native.RUN/"manifest.json",o.native.RUN_SEAL)
        pre=cls.manifest["preflight"];cls.elf=Path(pre["input_elf"])
        cls.blob=cls.elf.read_bytes()
        if o.life.digest(cls.elf)!=o.ELF_SHA:raise ValueError("Fixture ELF drift")
        cls.symbols=dict(pre["symbols"])
        for name in ("query","key","value","descriptor","seed"):
            cls.symbols[name]=o.native.software.shared._elf_symbol(cls.elf,o.native.software.shared.LLVM/"llvm-readelf",name)
        cls.rows=o.native.commit_rows(o.native.RUN/"commit_trace.csv")

    def test_actual_all_scalar_replay(self):
        model,result=o.replay(self.blob,self.symbols,self.rows)
        self.assertEqual(result["matched_retirements"],103458)
        self.assertEqual(result["independently_executed_steps"],103459)
        self.assertEqual(len(model.traps),1)

    def test_real_first_GPR_corruption_rejected(self):
        rows=list(self.rows);index=next(i for i,r in enumerate(rows) if r["event"]=="retire" and r["rd"])
        rows[index]=dict(rows[index],rd_wdata=rows[index]["rd_wdata"]^1)
        with self.assertRaisesRegex(ValueError,"GPR result"):o.replay(self.blob,self.symbols,rows)

    def test_real_partial_trace_rejected(self):
        rows=[r for r in self.rows if r["event"]!="retire" or r["order"]<100]
        with self.assertRaisesRegex(ValueError,"Partial scalar"):o.replay(self.blob,self.symbols,rows)

    def test_step_bound_rejected(self):
        with self.assertRaisesRegex(ValueError,"bound exceeded"):
            o.replay(self.blob,self.symbols,self.rows,max_steps=2)

    def corrupt_retirement(self, predicate, field, mask=1):
        rows=list(self.rows)
        index=next(i for i,r in enumerate(rows) if r["event"]=="retire" and predicate(r))
        rows[index]=dict(rows[index],**{field:rows[index][field]^mask})
        with self.assertRaises(ValueError):o.replay(self.blob,self.symbols,rows)

    def test_real_branch_PC_corruption(self):
        self.corrupt_retirement(lambda r:r["insn"]&127==0x63,"pc",4)

    def test_real_signed_load_corruption(self):
        self.corrupt_retirement(lambda r:r["insn"]&0x707f==0x1003 and r["rd"],"rd_wdata",1<<63)

    def test_real_store_corruption(self):
        self.corrupt_retirement(lambda r:r["mem_wmask"]!=0,"mem_wdata")

    def test_real_CSR_corruption(self):
        self.corrupt_retirement(lambda r:r["insn"]&127==0x73 and r["rd"],"rd_wdata")

    def test_real_handler_cause_corruption(self):
        self.corrupt_retirement(lambda r:r["insn"]>>20==0x342 and r["rd"],"rd_wdata")

    def test_real_snapshot_load_corruption(self):
        base=self.symbols["boundary_snapshots"]
        self.corrupt_retirement(lambda r:base<=r["mem_addr"]<base+16384 and r["mem_rmask"] and r["rd"],"rd_wdata")

    def test_actual_source_and_elaboration_contract(self):
        seal=o.life.read_bound(o.CANDIDATE/"candidate-seal.json",o.CANDIDATE_SHA)
        pins=o.life.merge_pins(seal["input_pins"],seal["output_pins"])
        path=o.native.software.BUILD/"build-source-pins.json"
        sources=o.life.read_bound(path,pins[str(path)])
        _,contract=o.source_contract(sources,pins)
        self.assertEqual(contract["elaborated_GPR_scope"],o.GPR_SCOPE)
        self.assertTrue(contract["dirty_and_MRET_source_anchors_verified"])

    def test_wrong_elaborated_GPR_selection_rejected(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        seal=o.life.read_bound(o.CANDIDATE/"candidate-seal.json",o.CANDIDATE_SHA)
        pins=o.life.merge_pins(seal["input_pins"],seal["output_pins"])
        path=o.native.software.BUILD/"build-source-pins.json"
        sources=o.life.read_bound(path,pins[str(path)])
        wrong=SimpleNamespace(hierarchy={o.GPR_SCOPE:{"chksum":"0"}})
        with patch("inventory_operand_debug.Design",return_value=wrong):
            with self.assertRaisesRegex(ValueError,"Wrong elaborated FF GPR"):
                o.source_contract(sources,pins)


class SourceContractNegativeTest(unittest.TestCase):
    def test_comment_cannot_supply_anchor(self):
        for text in ("// mem <= '0;\n", "/* mem <= '0; */"):
            with self.assertRaises(ValueError):o.source_anchors(text,["mem <= '0;"])

    def test_wrong_reset_value_rejected(self):
        with self.assertRaises(ValueError):o.source_anchors("mem <= '1;",["mem <= '0;"])


class NativeByteBindingTest(unittest.TestCase):
    def fixture(self):
        m=model([imm(1,0,1)])
        m.commands=[dict(word=i,fault=False) for i in range(8)]
        m.vector_effects=[dict(kind="seed",vd=i,data="1234") for i in range(32)]
        arch=dict(commands=[dict(word=i,fault=0,phase=i,seq=100+i) for i in range(8)],
                  uops=[dict(insn=7,order=i) for i in range(32)])
        rows=[dict(event="write",arch_seq=str(i),be="03",addr=str(i*4),lane="0",wdata="3412") for i in range(32)]
        return m,arch,rows

    def test_independent_vector_byte_corruption(self):
        m,arch,rows=self.fixture();rows[0]["wdata"]="3413"
        with self.assertRaisesRegex(ValueError,"vector byte mismatch"):o.bind_native_effects(m,arch,rows)

    def test_missing_vector_byte(self):
        m,arch,rows=self.fixture();rows[0]["be"]="01"
        with self.assertRaisesRegex(ValueError,"Incomplete"):o.bind_native_effects(m,arch,rows)

    def test_extra_or_duplicate_vector_byte(self):
        m,arch,rows=self.fixture();rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):o.bind_native_effects(m,arch,rows)


if __name__ == "__main__":
    unittest.main()
