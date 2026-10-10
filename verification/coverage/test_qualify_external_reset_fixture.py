import copy
import unittest
import qualify_external_reset_fixture as m


class ActualFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=m.life.read_bound(m.run.OUT.with_name(m.run.OUT.name+'.prepared.json'),m.SEAL)
        cls.pre=m.life.read_bound(m.run.PRE/'preflight.json',m.run.PRE_SHA)
        reader=m.events.run.shared.template.s.LLVM/'llvm-readelf'
        cls.snapshot=m.events.run.shared.template.s._elf_symbol(m.run.PRE/'input.elf',reader,'snapshot')

    def test_actual_stage_fourcycles_all_AXI_channels(self):
        q=m.wave(m.VCD,self.plan['selection'],self.pre['symbols']['source']+128,self.snapshot)
        self.assertEqual(q['actual_stage'],6); self.assertEqual(q['reset_negedges'],4)
        self.assertEqual(q['phases'],[dict(ar=0,r=0,aw=0,w=0,b=0),dict(ar=1,r=64,aw=32,w=256,b=32)])
        self.assertEqual(q['pending'],0)

    def test_wrong_stage_guard_and_source_rejected(self):
        for mutation in ('stage','guard','source','snapshot'):
            c=copy.deepcopy(self.plan['selection']); source=self.pre['symbols']['source']+128; snapshot=self.snapshot
            if mutation=='stage': c['ext_value']=5
            elif mutation=='guard': c['ext_guard']=c['ext_target']
            elif mutation=='source': source+=16
            else: snapshot+=16
            with self.assertRaises(ValueError): m.wave(m.VCD,c,source,snapshot)

    def test_actual_epoch0_seed_and_completed_multiply_bytes(self):
        _,cr=m.events.run.reset.read_csv(m.run.OUT/'commit_trace.csv')
        _,vr=m.events.run.reset.read_csv(m.run.OUT/'vector_trace.csv')
        epochs,_=m.events.run.reset.split_epochs(cr,vr)
        self.assertGreater(m.epoch0_bytes(epochs[0][1]),4096)
        rows=copy.deepcopy(epochs[0][1]); writer=next(r for r in rows if r['event']=='write')
        writer['wdata']='%016x'%(int(writer['wdata'],16)^1)
        with self.assertRaises(ValueError): m.epoch0_bytes(rows)

    def test_orphan_backend_rejected(self):
        _,cr=m.events.run.reset.read_csv(m.run.OUT/'commit_trace.csv')
        _,vr=m.events.run.reset.read_csv(m.run.OUT/'vector_trace.csv')
        epochs,_=m.events.run.reset.split_epochs(cr,vr)
        bad=copy.deepcopy(epochs[1][1]); next(r for r in bad if r['event']=='write')['vid']='255'
        with self.assertRaises(ValueError): m.events.backend(epochs[1][0],bad,set())

    def test_precise_fullgold_rejects_byte_or_CSR_change(self):
        values={('g75_result',0):679,('g75_result',4):0,('num_failed',0):0,('tohost',0):1}
        values.update({('fpar_vrf',i*8):m.gold.expected_word(i) for i in range(512)})
        values.update({('fpar_csr',i*8):v for i,v in enumerate((512,11,0,0,33))})
        m.gold.oracle(lambda n,o=0,size=8:values[n,o])
        for name,offset in (('fpar_vrf',24),('fpar_csr',32)):
            bad=dict(values); bad[name,offset]^=1
            with self.assertRaises(ValueError): m.gold.oracle(lambda n,o=0,size=8:bad[n,o])


if __name__=='__main__': unittest.main()
