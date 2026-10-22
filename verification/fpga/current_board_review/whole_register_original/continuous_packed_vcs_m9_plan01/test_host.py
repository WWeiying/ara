"""Bounded full1134 synthetic stream plus local adversarial gates; no DUT/ref."""
import ast
import csv
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import checker as c
import host_records as h
from stream import one_pass

GENERIC=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/verification/ara_verify/trace.py')

class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.spec=c.specification()
    def state(self):return c.Strict(self.spec)
    def test_full_positive_single_stream(self):
        with tempfile.TemporaryDirectory(prefix='whole1134_host_') as d:
            p=Path(d)/'trace.csv'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=h.FIELDS);w.writeheader();w.writerows(h.protocol(h.records(self.spec)))
            generic=c.load('whole_host_generic',GENERIC);state=self.state()
            general,report,digest,identity=one_pass(p,state,generic,lambda:None)
            self.assertEqual((report['calls'],report['output_byte_checks'],report['helper_instructions']),(1134,1233792,21366))
            self.assertEqual((report['fresh_input_stores'],report['fresh_output_stores'],report['output_word_reads']),(145152,154224,154224))
            self.assertEqual(report['owners']['required_owners'],4266)
            self.assertEqual(general['backend_uop_alloc_count'],4266)
            self.assertEqual(digest,c.sha(p));self.assertEqual(report['vstart_reads'],2268)
            self.__class__.positive=dict(rows=state.rows,retired=state.retired,owners=report['owners'],generic=general,
                calls=report['calls'],helper_instructions=report['helper_instructions'],raw_bytes=identity[2],raw_sha256=digest)
    def test_fresh_oracle_status_negatives(self):
        for mutation,match in [('fresh_interval','Incomplete fresh setup'),('input','Fresh input value'),
              ('missing_word','Incomplete original1088'),('guard','Original all-byte'),('result','Original all-byte'),
              ('vstart','Actual vstart'),('status','Returned whole status')]:
            with self.subTest(mutation=mutation):
                state=self.state()
                with self.assertRaisesRegex(ValueError,match):
                    for row in h.protocol(h.records(self.spec,mutation,limit=2)):state.consume(row)
    def test_wrong_owner_id(self):
        state=self.state()
        with self.assertRaisesRegex(ValueError,'completion owner identity'):
            for row in h.protocol(h.records(self.spec,limit=1),'wrong_id'):state.consume(row)
    def owner_fixture(self):
        owners=c.Owners(self.spec,c.read(c.REF/'tuples.json')['cases'])
        for seq,e in enumerate(owners.expected):
            row=dict(insn=f'{e["insn"]:08x}',order=str(seq),trans_id=str(seq%8),port='0',pc=f'{e["pc"]:x}')
            for event in ['cvx_req','arch_start']+(['uop_alloc','uop_done'] if e['required'] else [])+['retire']:
                owners.consume(dict(row,event=event))
        return owners
    def test_every_required_owner_pair_deletion(self):
        owners=self.owner_fixture();self.assertEqual(owners.finish()['allowed_empty_targets'],270)
        rejected=0
        for seq,e in enumerate(owners.expected):
            if not e['required']:continue
            a=owners.arch[seq];a['allocs']=a['dones']=0;owners.allocs-=1;owners.dones-=1
            with self.assertRaisesRegex(ValueError,'Missing required owner'):owners.finish()
            a['allocs']=a['dones']=1;owners.allocs+=1;owners.dones+=1;rejected+=1
        self.assertEqual(rejected,4266)
    def test_payload_cvx_id_binding(self):
        owners=self.owner_fixture();a=owners.arch[0];a['trans']^=1
        with self.assertRaisesRegex(ValueError,'CVX transaction identity'):owners.finish()
    def test_setup_cache_mutations(self):
        active=dict(ordinal=0,tuple=dict(start=0),returned=True,reads=set(range(1088)),csrs=[0,0],preloads=2,stores=1)
        for key,value in [('returned',False),('reads',frozenset(range(1080))),('stores',2),('csrs',(0,1))]:
            a=deepcopy(active);cache=c.cache.CompletionCache();cache.finish(a);a[key]=value
            with self.assertRaisesRegex(ValueError,'state changed'):cache.finish(a)
    def test_exact_real_abi_and_unknown_source(self):
        state=self.state();rows=list(h.protocol(h.records(self.spec,limit=0)))
        for row in rows:state.consume(row)
        self.assertEqual(state.regs[2],state.s['__stack_top'])
        # Actual original-main prologue saves untouched s0 before assigning it.
        pc,ins=next((pc,ins) for pc,ins in state.code.items() if state.s['whole_original_main']<pc<state.s['whole_original_main']+128
                    and (d:=c.memory_op(ins)) and d['kind']=='write' and d['register']==8)
        d=c.memory_op(ins);addr=(state.regs[d['base']]+d['offset'])&c.MASK64
        row=dict(rows[-1],pc=f'{pc:x}',insn=f'{ins:x}',rd='0',rd_wdata='0',mem_addr=f'{addr:x}',
            mem_rmask='0',mem_wmask=f'{((1<<d["size"])-1)<<(addr%8):x}',mem_wdata='0',order=str(state.retired),cycle=str(state.cycle+1))
        state.consume(row);del state.regs[8]
        with self.assertRaisesRegex(ValueError,'store enables/value/register'):
            state.consume(dict(row,order=str(state.retired),cycle=str(state.cycle+1)))
    def test_reset_profile_mismatch(self):
        old=c.read
        def read(p):
            x=old(p)
            if Path(p)==c.HERE/'reset_profile.json':x['FpgaEn']=1
            return x
        with patch.object(c,'read',read),self.assertRaisesRegex(ValueError,'FF reset'):self.state()
    def test_ctrl_wrong_raw_exit(self):
        state=self.state();s=state.s;pc=state.spec['exit_store'];d=c.memory_op(state.code[pc])
        state.retired=1;state.regs[d['base']]=state.spec['ctrl']-d['offset'];state.regs[10]=1
        row=dict(cycle='1',event='retire',order='1',port='0',trans_id='-1',pc=f'{pc:x}',insn=f'{state.code[pc]:x}',
                 rd='0',rd_wdata='0',mem_addr=f'{state.spec["ctrl"]:x}',mem_rmask='0',mem_wmask='ff',mem_wdata='1',trap='0')
        with self.assertRaisesRegex(ValueError,'CTRL raw0'):state.consume(row)
    def test_console_failure_veto(self):
        c.console_gate(c.EXPECTED_TEXT,False)
        for text in (c.EXPECTED_TEXT+'RVV_WHOLE_DETAIL bad\n',c.EXPECTED_TEXT.replace('1134','1133'),c.EXPECTED_TEXT*2):
            with self.assertRaises(ValueError):c.console_gate(text,False)
    def test_pure_semantics_identical(self):
        def functions(p):
            text=p.read_text();return {n.name:ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
        a,b=functions(c.REF/'audit.py'),functions(c.HERE/'helper_semantics.py')
        for name in ('descriptor','next_helper_pc'):self.assertEqual(a[name],b[name])
    def test_actual_validator_composition_missing_pair(self):
        owners=self.owner_fixture()
        # Real validator permits pair absence; per-owner gate must reject despite surplus.
        class PairGate:
            def consume(self,row):pass
            def finish(self):return {}
        e=owners.expected[0]
        rows=[]
        for i,event in enumerate(('cvx_req','arch_start','cvx_resp','retire')):
            rows.append(dict.fromkeys(h.FIELDS,'0'));rows[-1].update(cycle=str(i),event=event,insn=f'{e["insn"]:x}')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.csv'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=h.FIELDS);w.writeheader();w.writerows(rows)
            generic=c.load('whole_host_schema_generic',GENERIC)
            result,_,_,_=one_pass(p,PairGate(),generic,lambda:None)
            self.assertNotIn('status',result);self.assertEqual(result['backend_uop_alloc_count'],0)
        owners.arch[0]['allocs']=owners.arch[0]['dones']=0;owners.allocs-=1;owners.dones-=1
        with self.assertRaisesRegex(ValueError,'Missing required owner'):owners.finish()

def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Host)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    pins={str(c.HERE/n):c.sha(c.HERE/n) for n in ('checker.py','stream.py','helper_semantics.py','reset_profile.json','host_records.py','test_host.py')}
    pins[str(GENERIC)]=c.sha(GENERIC)
    c.save(c.HERE/'host02.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'NOT_PASS',
        failures=len(result.failures)+len(result.errors),tests=result.testsRun,full_positive_shapes=['whole_all'] if hasattr(Host,'positive') else [],
        actual_abi_entry_checked=result.wasSuccessful(),pins=pins,positive=getattr(Host,'positive',None),
        scope='Host synthetic actual-PC full1134; not DUT or reference execution'))
    return int(not result.wasSuccessful())

if __name__=='__main__':raise SystemExit(main())
