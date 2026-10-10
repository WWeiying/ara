import unittest
from types import FunctionType
import collect_akv_canonical_alias794_sd_v2 as v
import run_akv_canonical_alias794 as r


class SD(unittest.TestCase):
    def test_all_FS_VS_states_both_write_SD_bits(self):
        for fs in range(4):
            for vs in range(4):
                for write_sd in (0,1):
                    value=0xa00000000|(fs<<13)|(vs<<9)|(write_sd<<63)
                    expected=0xa00000000|(fs<<13)|(vs<<9)|(int(fs==3 or vs==3)<<63)
                    self.assertEqual(v.derived_status(value),expected)

    def test_XS_contract_not_expanded(self):
        for xs in (1,2,3):
            with self.assertRaises(ValueError):v.derived_status(0xa00000000|(xs<<15))

    def model(self):
        pre=v.life.read_bound(r.PRE/'preflight-manifest.json',r.PRE_SHA)
        return v.Model(r.ELF.read_bytes(),pre['symbols'])

    def test_exact_startup_write_and_dirty(self):
        m=self.model();m.csr_write(0x300,0xa00006600)
        self.assertEqual(m.csr[0x300],0x8000000a00006600)
        m.csr_write(0x300,0x8000000a00000000)
        self.assertEqual(m.csr[0x300],0xa00000000)
        m.dirty(True);self.assertEqual(m.csr[0x300],0x8000000a00000600)

    def test_bad_status_bits_still_rejected(self):
        for bits in (1<<15,1<<16,1<<17,1<<20):
            with self.assertRaises(ValueError):self.model().csr_write(0x300,0xa00000000|bits)

    def test_missing_or_wrong_SD_read_rejected(self):
        e=dict(pc=0x8000255c,insn=0x30002573,rd=10,rd_wdata=0x8000000a00006600,
               mem_addr=0,mem_rmask=0,mem_wmask=0,trap=0)
        for actual in (0xa00006600,0x8000000a00006000):
            with self.assertRaisesRegex(ValueError,'GPR result mismatch'):
                v.original.old.isa.base.compare_retirement(e,dict(e,rd_wdata=actual),32191)

    def test_other_fields_not_masked(self):
        e=dict(pc=0x8000255c,insn=0x30002573,rd=10,rd_wdata=0x8000000a00006600,
               mem_addr=0,mem_rmask=0,mem_wmask=0,trap=0)
        for key in ('pc','insn','rd','mem_addr','mem_rmask','mem_wmask','trap'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                v.original.old.isa.base.compare_retirement(e,dict(e,**{key:e[key]^1}),32191)

    def test_actual_frozen_source(self):v.life.check(v.source())

    def ecall(self):
        e=dict(pc=0x80003a24,insn=0x73,rd=0,mem_addr=0,mem_rmask=0,mem_wmask=0,trap=1)
        r=dict(e,order=50405,rd_wdata=0,mem_wdata=0)
        n=dict(pc=0x80002000,insn=0x342022f3,trap=0,rd=5,rd_wdata=9)
        return e,r,n

    def test_scalar_ECALL_exact_record(self):
        e,r,n=self.ecall();v.ecall_retirement(e,r,n,e['pc'],n['pc'])

    def test_scalar_ECALL_must_not_be_skipped_or_relaxed(self):
        e,r,n=self.ecall()
        for key in ('pc','insn','rd','mem_addr','mem_rmask','mem_wmask','trap','rd_wdata','mem_wdata'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                v.ecall_retirement(e,dict(r,**{key:r[key]^1}),n,e['pc'],n['pc'])

    def test_scalar_ECALL_handler_exact_cause_and_PC(self):
        e,r,n=self.ecall()
        for key in ('pc','insn','trap','rd','rd_wdata'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                v.ecall_retirement(e,r,dict(n,**{key:n[key]^1}),e['pc'],n['pc'])


class Actual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run=v.life.OUT/'akv-canonical-alias794-old-image-parent-20261008-01'
        m=v.life.read_bound(run/'manifest.json','f777d171de39027b9d0b7fdd4b7fd88f2c3ad5438a27e9f79eb9cbcde0c62de1')
        cls.rows=[r for r in v.original.old.isa.base.native.commit_rows(run/'commit_trace.csv') if r['event']=='retire']
        class Recording(v.Model):
            def __init__(self,*args):super().__init__(*args);self.effects=[]
            def step(self):
                e=super().step();self.effects.append(e);return e
        replay=FunctionType(v.replay.__code__,dict(v.replay.__globals__,Model=Recording))
        from pathlib import Path
        elf=Path(m['preflight']['input_elf']);v.require(v.life.digest(elf)==m['pins'][str(elf)],'Same actual native ELF')
        cls.model,cls.result=replay(elf.read_bytes(),m['preflight']['symbols'],cls.rows)

    def test_actual_complete_trace_zero_skip(self):
        self.assertEqual(self.result['matched_retirements'],116614)
        self.assertEqual(self.result['steps'],116614);self.assertEqual(self.result['skipped_retirements'],0)
        self.assertEqual(self.result['GPR_writes'],70418);self.assertFalse(self.result['native_custom_Spike'])
        self.assertEqual(len(self.model.effects),len(self.rows))

    def test_actual_SD_exact_negative(self):
        i=32191;e=self.model.effects[i];r=self.rows[i]
        self.assertEqual((e['pc'],e['insn'],e['rd_wdata']),(0x8000255c,0x30002573,0x8000000a00006600))
        with self.assertRaises(ValueError):v.original.old.isa.base.compare_retirement(e,dict(r,rd_wdata=r['rd_wdata']^(1<<63)),i)

    def test_actual_both_trapseq_cause_memory_negatives(self):
        indices=[i for i,e in enumerate(self.model.effects) if e['trap']]
        self.assertEqual(len(indices),2)
        for i in indices:
            e,r,n=self.model.effects[i],self.rows[i],self.rows[i+1]
            pc,handler=self.model.symbols['akva_ecall'],self.model.symbols['akva_handler']
            v.ecall_retirement(e,r,n,pc,handler)
            for bad in (dict(r,trap=0),dict(r,mem_wmask=1,mem_wdata=1),dict(r,pc=r['pc']+4)):
                with self.assertRaises(ValueError):v.ecall_retirement(e,bad,n,pc,handler)
            for bad in (dict(n,pc=n['pc']+4),dict(n,rd_wdata=8)):
                with self.assertRaises(ValueError):v.ecall_retirement(e,r,bad,pc,handler)

    def test_actual_fflags_and_store_memory_negatives(self):
        flag=next(i for i,e in enumerate(self.model.effects) if e['insn']&127==0x73 and e['insn']>>20==1
            and e['insn']>>12&7==2 and e['insn']>>15&31==0 and e['rd'])
        store=next(i for i,e in enumerate(self.model.effects) if e['mem_wmask'])
        for i,key in ((flag,'rd_wdata'),(store,'mem_wdata')):
            e,r=self.model.effects[i],self.rows[i]
            with self.assertRaises(ValueError):v.original.old.isa.base.compare_retirement(e,dict(r,**{key:r[key]^1}),i)


if __name__=='__main__':unittest.main()
