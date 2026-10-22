"""Focused oracle/endpoint/owner negatives; synthetic rows are not DUT evidence."""
import copy
import json
from pathlib import Path
import unittest
import observer as o
import csv_check as c
import source_owners as owners

HERE=Path(__file__).resolve().parent

def spec(n):
    return json.loads((HERE/'software01'/f'scenario{n}'/'soc.spec.json').read_text())

def row(pc=0,insn=0,**fields):
    r={k:'0' for k in c.FIELDS}
    r.update(event='retire',pc=f'{pc:x}',insn=f'{insn:x}')
    r.update({k:str(v) for k,v in fields.items()})
    return r

def gold(s,n,phase):
    m=o.expected(s,64,phase,n)
    if phase:
        for i,b in enumerate((0x800).to_bytes(8,'little')):m[s['fx_records']+24+i]=b
    return m

def lifecycle(n,omit=None,mutate=None):
    s=spec(n);q=owners.MemoryOwners(s)
    mem=gold(s['symbols'],n,0);cfg=o.spec_values(64,n)
    for i,site in enumerate(owners.recipe(s)):
        for j,event in enumerate(('arch_start','uop_alloc','cvx_req','uop_done','cvx_resp','retire')):
            if omit==i and event in ('uop_alloc','uop_done'):continue
            r=row(site['pc'],site['insn'],event=event,order=i,trans_id=i,port=i%2,cycle=i*10+j)
            if mutate:mutate(r,i,event)
            q.row(r,{10:cfg['base']},{0xc20:8,0xc21:24,8:0},mem)
    return q.finish()

class Host(unittest.TestCase):
    def test_actual_c_oracle(self):
        for n in (0,3):
            p=HERE/'software01'/f'scenario{n}'
            self.assertEqual(o.host_check((p/'host.stdout').read_text(),64,n),2836)

    def test_exact_original_defined_outputs(self):
        self.assertEqual([o.output_value(64,1,i,0) for i in range(1,9)],
                         [11,48,85,122,None,None,None,None])
        self.assertEqual([o.output_value(64,1,i,3) for i in range(130)],[91]*130)
        for n in (0,3):
            self.assertEqual([o.output_value(64,0,i,n) for i in range(130)],[91]*130)
        self.assertEqual(o.spec_values(64,0)['returned_vl'],4)
        self.assertEqual(o.spec_values(64,3)['returned_vl'],8)

    def test_complete_defined_bytes_mutation(self):
        for n in (0,3):
            s=spec(n)['symbols']
            for phase in (0,1):
                m=gold(s,n,phase);self.assertGreater(o.compare(m,s,64,phase,n),21000)
            addresses=[s['fx_out']+i*8 for i in range(130) if o.output_value(64,1,i,n) is not None]
            addresses += [s['fx_mask']+i for i in range(16)]
            addresses += [s['fx_pages']+i for i in (0,4064,4095,4096,8191,8192,12288,16384,16392,20479)]
            addresses += [s[x] for x in ('fx_return','fx_guard_lo','fx_guard_hi','fx_unexpected','fx_count','fx_records')]
            addresses += [s['fx_return']+4,s['fx_post']+16]
            for a in addresses:
                bad=dict(m);bad[a]^=1
                with self.subTest(scenario=n,address=hex(a)),self.assertRaises(ValueError):o.compare(bad,s,64,1,n)
            del m[s['fx_out']+129*8]
            with self.assertRaises(ValueError):o.compare(m,s,64,1,n)

    def test_only_final_fof_four_tail_words_unconstrained(self):
        for n in (0,3):
            s=spec(n)['symbols']
            for phase in (0,1):
                for value in (0,255):
                    m=gold(s,n,phase)
                    for a in range(s['fx_out']+40,s['fx_out']+72):m[a]=value
                    if n==0 and phase==1:o.compare(m,s,64,phase,n)
                    else:
                        with self.assertRaises(ValueError):o.compare(m,s,64,phase,n)

    def test_full_checkpoint_read_recipe(self):
        for n in (0,3):
            q=c.Checker(spec(n))
            self.assertEqual(len(q.expected_reads(0)),2722)
            self.assertEqual(len(q.expected_reads(1)),2718 if n==0 else 2722)
            self.assertEqual(q.regs,{0:0})

    def test_all_four_memory_owners(self):
        for n in (0,3):
            r=lifecycle(n)
            self.assertEqual((r['memory_owner_count'],r['helper_owner_count'],r['memory_allocations']),(4,3,4))
            self.assertEqual(r['target_returned_vl'],4 if n==0 else 8)

    def test_deleting_complete_non_target_pair_fails(self):
        for n in (0,3):
            for i in range(4):
                with self.subTest(scenario=n,owner=i),self.assertRaises(ValueError):lifecycle(n,omit=i)

    def test_owner_transaction_completion_and_exception_fail(self):
        for field,value,event in (('trans_id','7','uop_done'),('port','7','uop_done'),
                                  ('trap','1','cvx_resp'),('insn','1057c07','uop_alloc')):
            def mutate(r,i,e):
                if i==0 and e==event:r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):lifecycle(0,mutate=mutate)

    def test_empty_owner_and_wrong_fof_context_fail(self):
        for n in (0,3):
            s=spec(n);cfg=o.spec_values(64,n);site=owners.recipe(s)[2]
            r=row(site['pc'],site['insn']);q=owners.MemoryOwners(s)
            q.retired=[{},{}]
            mem=gold(s['symbols'],n,0)
            for csrs in ({0xc20:0,0xc21:24,8:0},{0xc20:4,0xc21:24,8:0},{0xc20:8,0xc21:24,8:1}):
                with self.assertRaises(ValueError):q.row(r,{10:cfg['base']},csrs,mem)
            mem[s['symbols']['fx_mask']]^=1
            with self.assertRaises(ValueError):q.row(r,{10:cfg['base']},{0xc20:8,0xc21:24,8:0},mem)

    def test_actual_soc_endpoint(self):
        for n in (0,3):
            for raw in (0,1,17):
                q=c.Checker(spec(n));q.started=q.completed=True;q.regs={0:0,5:0xd0000000,10:raw}
                pc=q.spec['exit_store'];self.assertEqual(q.code[pc],0x00a2b023)
                self.assertNotIn('tohost',q.s)
                r=row(pc,q.code[pc],mem_addr='d0000000',mem_wmask='ff',mem_wdata=f'{raw:x}')
                if raw:
                    with self.assertRaises(ValueError):q.row(r)
                else:q.row(r);self.assertEqual(q.ctrl,[0])

    def test_unused_helper_every_pc_and_wrong_target_encoding(self):
        for n in (0,3):
            s=spec(n)
            for pc in s['unused']:
                q=c.Checker(s)
                with self.assertRaises(ValueError):q.row(row(pc,q.code[pc]))
            q=c.Checker(s);pc=s['helper'][3]
            self.assertEqual(q.code[pc],0x01057c07 if n==0 else 0x00057c07)
            with self.assertRaises(ValueError):q.row(row(pc,q.code[pc]^0x1000000))

    def test_truncated_scope_or_wrong_backend_fails(self):
        for n in (0,3):
            with self.assertRaises(ValueError):owners.Checker(spec(n)).finish()
            for change in ({'backend':'spike'},{'scenario':1},{'sew':8}):
                s=spec(n);s.update(change)
                with self.assertRaises(ValueError):owners.Checker(s)

if __name__=='__main__':unittest.main(verbosity=2)
