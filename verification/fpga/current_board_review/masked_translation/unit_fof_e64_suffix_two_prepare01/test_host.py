"""Small artificial-row negatives; never claimed as a DUT trace acceptance."""
import copy
import json
from pathlib import Path
import unittest
import observer as o
import csv_check as c

HERE=Path(__file__).resolve().parent

def spec(scenario):
    return json.loads((HERE/'software01'/f'scenario{scenario}'/'soc.spec.json').read_text())

def row(pc,insn):
    r={k:'0' for k in c.FIELDS}
    r.update(event='retire',pc=f'{pc:x}',insn=f'{insn:x}')
    return r

def completed_exit(scenario=1,value=0):
    q=c.Checker(spec(scenario))
    q.started=q.completed=True
    q.regs[5]=0xd0000000
    q.regs[10]=value
    pc=q.spec['exit_store']
    r=row(pc,q.code[pc])
    r.update(mem_addr='d0000000',mem_wmask='ff',mem_wdata=f'{value:x}')
    return q,r

class Host(unittest.TestCase):
    def test_actual_host_models(self):
        for scenario in (1,2):
            p=HERE/'software01'/f'scenario{scenario}'
            self.assertEqual(o.host_check((p/'host.stdout').read_text(),64),2836)

    def test_all_output_and_pages_bytes(self):
        for scenario in (1,2):
            s=spec(scenario)['symbols']
            for phase in (0,1):
                m=o.expected(s,64,phase)
                if phase:
                    for i,b in enumerate((0x800).to_bytes(8,'little')):m[s['fx_records']+24+i]=b
                self.assertGreater(o.compare(m,s,64,phase),21000)
            mutations={
                'active':s['fx_out']+8,'masked_first':s['fx_out']+40,
                'masked_last':s['fx_out']+64,'guard0':s['fx_out'],'guard9':s['fx_out']+72,
                'allocation_end':s['fx_out']+129*8,'repeated_byte_91':s['fx_out']+41,
                'mask':s['fx_mask'],'mask_tail':s['fx_mask']+15,
                'source':s['fx_pages']+4064,'protected_memory':s['fx_pages']+8191,
                'protected_leaf':s['fx_pages']+16392,'vl':s['fx_return'],
                'vstart':s['fx_return']+4,'post_start':s['fx_post']+16,
                'unexpected_fault':s['fx_records'],'outer_guard':s['fx_guard_hi']}
            for name,address in mutations.items():
                bad=dict(m);bad[address]^=1
                with self.subTest(scenario=scenario,mutation=name),self.assertRaises(ValueError):
                    o.compare(bad,s,64,1)
            del m[s['fx_out']+129*8]
            with self.assertRaises(ValueError):o.compare(m,s,64,1)

    def test_no_undefined_suffix(self):
        self.assertEqual([o.output_value(64,1,i) for i in range(1,9)],
                         [11,48,85,122,91,91,91,91])
        self.assertTrue(all(o.output_value(64,p,i) is not None for p in (0,1) for i in range(130)))

    def test_soc_actual_elf_ctrl_row_no_tohost(self):
        for scenario in (1,2):
            q,r=completed_exit(scenario)
            self.assertNotIn('tohost',q.s)
            self.assertEqual(q.code[q.spec['exit_store']],0x00a2b023)
            q.row(r)
            self.assertEqual(q.ctrl,[0])
            self.assertTrue(q.exited)

    def test_soc_rejects_spike_htif_one(self):
        q,r=completed_exit(value=1)
        with self.assertRaises(ValueError):q.row(r)

    def test_soc_rejects_nonzero_exit(self):
        q,r=completed_exit(value=17)
        with self.assertRaises(ValueError):q.row(r)

    def test_soc_rejects_exit_before_completion(self):
        q,r=completed_exit();q.completed=False
        with self.assertRaises(ValueError):q.row(r)

    def test_soc_rejects_exit_register_or_byte_enable(self):
        for field,value in (('mem_wdata','1'),('mem_wmask','f'),('mem_addr','d0000008')):
            q,r=completed_exit();r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):q.row(r)

    def test_soc_rejects_second_exit_and_after_exit_effect(self):
        q,r=completed_exit();q.row(r);r['order']='1'
        with self.assertRaises(ValueError):q.row(r)
        q,r=completed_exit();q.row(r)
        r=row(q.spec['park'],q.code[q.spec['park']]);r.update(order='1',rd='1',rd_wdata='1')
        with self.assertRaises(ValueError):q.row(r)

    def test_unused_helper_all_interiors_and_duplicate(self):
        for scenario in (1,2):
            s=spec(scenario)
            for pc in s['unused']:
                q=c.Checker(s)
                with self.subTest(scenario=scenario,pc=pc),self.assertRaises(ValueError):
                    q.row(row(pc,q.code[pc]))
            q=c.Checker(s);q.cap=3;q.step=11
            pc=s['helper'][3]
            with self.assertRaises(ValueError):q.row(row(pc,q.code[pc]))

    def test_target_pc_code_swapped(self):
        q=c.Checker(spec(1));pc=q.spec['helper'][3]
        self.assertEqual(q.code[pc],0x00057c07)
        with self.assertRaises(ValueError):q.row(row(pc,0x01057c07))
        q=c.Checker(spec(2));self.assertEqual(q.code[q.spec['helper'][3]],0x01057c07)

    def test_incomplete_finish_fails(self):
        with self.assertRaises(ValueError):c.Checker(spec(1)).finish()

    def test_backend_confusion_rejected(self):
        bad=spec(1);bad['backend']='spike'
        with self.assertRaises(ValueError):c.Checker(bad)
        bad=spec(1);bad['symbols']['tohost']=0x80001000
        with self.assertRaises(ValueError):c.Checker(bad)

    def test_startup_completion_only_exact_bss_clear(self):
        s=spec(1)['symbols']
        self.assertFalse(o.completion_phase(False,s['_start']+0x46,0x2b023,8,0,s))
        for pc,insn,width,value in ((s['_start']+0x48,0x2b023,8,0),
                                    (s['_start']+0x46,0x2b023,8,o.DONE),
                                    (s['_start']+0x46,0x2b023,4,0)):
            with self.assertRaises(ValueError):o.completion_phase(False,pc,insn,width,value,s)

if __name__=='__main__':unittest.main(verbosity=2)
