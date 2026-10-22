import copy
import json
import unittest
from pathlib import Path
import checker as o


class Oracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=json.loads((o.PILOT.parent/'software01/spike.symbols.json').read_text())
        for i,n in enumerate(('mx_case','mx_base','mx_store','mx_cases_done','mx_prefix')):
            cls.s[n]=0x90000000+128*i

    def t(self,**kw):
        t=dict(unmapped=1,store=0,boundary=3,mode=2,split=0,gap=3);t.update(kw);return t

    def sample(self,t,phase):
        mem={a:0 if b is None else b for a,b in o.expected(self.s,t,phase,0).items()}
        count=(1+o.geom(t)['fault'] if phase==3 or (phase and not o.geom(t)['fault']) else int(phase>0))
        for n in range(count):
            for j,b in enumerate((0x800).to_bytes(8,'little')):mem[self.s['mx_records']+n*96+24+j]=b
        o.compare(mem,self.s,t,phase,0)
        return mem

    def test_all38_fullphases(self):
        manifest=json.loads((o.HERE.parent/'prepared01/manifest.json').read_text())
        cases=[c for c in manifest['original40'] if not c['accepted_m6']]
        self.assertEqual(len(cases),38)
        for c in cases:
            for phase in range(4):self.sample(c['parameters'],phase)

    def test_b1_no_completed_prefix(self):
        g=o.geom(self.t(boundary=1));self.assertEqual(g['start'],2);self.assertEqual(g['prefix'],[])
        self.sample(self.t(boundary=1,store=1),1)

    def test_alloff_does_not_trap_or_poison(self):
        t=self.t(mode=3,store=1);g=o.geom(t);self.assertFalse(g['fault'])
        self.assertNotIn('retry_mret',o.expected_actions(t))
        self.assertTrue(o.expected_actions(t).index('target')<o.expected_actions(t).index('repair_sfence'))

    def test_permission_retains_ppn_not_absent(self):
        u0=self.sample(self.t(unmapped=0),0);u1=self.sample(self.t(),0)
        a=self.s['mx_pages']+16384
        self.assertEqual(o.readint(u0,a),((self.s['mx_pages']>>12)<<10)|0xc9)
        self.assertEqual(o.readint(u1,a),0)
        self.assertNotIn('refill',o.expected_actions(self.t(unmapped=0)))

    def test_partial_not_relabelled_as_final(self):
        t=self.t();a=self.s['mx_fault']+64+128+2*5
        m=self.sample(t,1);m[a]^=77;o.compare(m,self.s,t,1,0)
        m=self.sample(t,3);a=self.s['mx_result']+64+128+2*5;m[a]^=77
        with self.assertRaises(ValueError):o.compare(m,self.s,t,3,0)

    def test_fulloracle_corruptions_rejected(self):
        t=self.t();s=self.s
        locations=[s['mx_result']+64+128+126,s['mx_out'],s['mx_out']+130,s['mx_out']+258,
            s['mx_input']+126,s['mx_input']+254,s['mx_offsets']+254,s['mx_mask']+15,
            s['mx_pages']+8191,s['mx_pages']+16392,s['mx_guard_lo'],s['mx_guard_hi'],
            s['mx_records']+16,s['mx_records']+56,s['mx_records']+24,s['mx_post']+16,s['mx_post']+24,
            s['mx_marker'],s['mx_restart'],s['mx_case'],s['mx_base'],s['mx_stride']]
        for a in locations:
            m=self.sample(t,3);m[a]^=8 if a==s['mx_records']+24 else 1
            with self.subTest(address=hex(a)),self.assertRaises(ValueError):o.compare(m,s,t,3,0)
        m=self.sample(t,3);del m[s['mx_pages']+8191]
        with self.assertRaises(ValueError):o.compare(m,s,t,3,0)

    def test_retry_gpr_pc_csr_mutations(self):
        t=self.t(boundary=1);g=o.geom(t);s=self.s
        regs=dict(zip(range(10,16),[o.VA+g['base'],s['mx_input'],s['mx_out']+2,s['mx_mask'],64,s['mx_stride']]))
        regs[28]=g['stride']&o.U64
        csr={0x341:s['fault_0_pc'],8:2,0xc20:8,0xc21:8,0x300:0x800}
        o.retry_context(s,t,regs,csr)
        for key in csr:
            bad=copy.copy(csr);bad[key]^=0x800 if key==0x300 else 1
            with self.assertRaises(ValueError):o.retry_context(s,t,regs,bad)
        for key in regs:
            bad=copy.copy(regs);bad[key]^=1
            with self.assertRaises(ValueError):o.retry_context(s,t,bad,csr)

    def test_store_prefix_vs_load_poison(self):
        self.assertEqual(o.data(self.t(store=1),2,2051),36)
        self.assertEqual(o.data(self.t(),2,2051),o.orig(2051)^91)

    def test_counts_vary_not_pilot_constant(self):
        _,a=o.check_counts([self.t()]);_,b=o.check_counts([self.t(boundary=1)])
        _,c=o.check_counts([self.t(mode=3)])
        self.assertNotEqual(a,b);self.assertNotEqual(b,c)


if __name__=='__main__':unittest.main(verbosity=2)
