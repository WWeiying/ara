"""Synthetic RVFI fixtures over the real linked ELF; not DUT measurements."""
import copy
import csv
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import collect_fence_t_u_padding_post as tool


class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads(tool.PLAN.read_bytes())
        build=tool.OUT/'fence-t-u-padding-build-parent-727-20261006-01'
        cls.metadata=json.loads((build/'elf_metadata.json').read_bytes())[0]
        cls.blob=(build/'input.elf').read_bytes()
        cls.syms={s['Symbol']['Name']['Name']:s['Symbol'] for s in cls.metadata['Symbols']}
        cls.code=tool.oracle.frozen.elf_instructions(cls.metadata,cls.blob)

    def fixture(self, ceiling=0):
        rows=[]
        def add(pc, **values):
            row=dict.fromkeys(tool.oracle.frozen.FIELDS,0)
            row.update(cycle=len(rows)+1,event='retire',order=len(rows),port=0,
                       trans_id=-1,pc=pc,insn=self.code[pc])
            row.update(values);rows.append(row)
        add(0x80000000)
        observed=self.syms['observed']['Value']+8
        stack=self.syms['probe_stack']['Value']+1024
        def capture(n):
            site=self.plan['proof']['sites'][n];add(int(site['fence_pc'],16))
            resume=int(site['resume_pc'],16);auipc=int(site['auipc_pc'],16)
            for i in range(67):
                pc=resume+4*i;word=self.code[pc];data={}
                if word & 127 in (0x23,0x27):
                    offset=((word>>25)<<5)|((word>>7)&31);reg=(word>>20)&31
                    if word & 127 == 0x27: value=tool.oracle.frozen.seed(n,reg,True)
                    elif offset==512:value=auipc
                    else:value=0 if reg==0 else stack if reg==2 else observed if reg==31 else tool.oracle.frozen.seed(n,reg,False)
                    data=dict(mem_addr=observed+offset,mem_wmask=255,mem_wdata=value)
                elif i==1:data=dict(rd=30,rd_wdata=auipc)
                add(pc,**data)
        capture(0);capture(1)
        add(self.syms['padding_enter_mret']['Value'])
        ecall=self.syms['padding_u_ecall']['Value'];add(ecall,trap=1)
        handler=self.syms['padding_handler'];ledger=self.syms['padding_trap']['Value']
        expected={8:1,16:8,24:ecall,32:0,40:0x6000}
        for pc in sorted(self.code):
            word=self.code[pc]
            if handler['Value']<=pc<handler['Value']+handler['Size'] and word&127==0x23:
                offset=((word>>25)<<5)|((word>>7)&31)
                add(pc,mem_addr=ledger+offset,mem_wmask=255,mem_wdata=expected[offset])
        add(self.syms['padding_return_mret']['Value']);capture(2)
        pc=next(pc for pc,w in self.code.items() if w>>20==0x7c5 and w&127==0x73 and
                (w>>12)&7==2 and (w>>15)&31==0 and (w>>7)&31!=0)
        add(pc,rd=(self.code[pc]>>7)&31,rd_wdata=ceiling)
        console=('fence_t_gap36_smoke rounds=2 checks=458 failures=0\n'
                 f'fence_t_u_padding_successor ceiling={ceiling} padding_witness={int(ceiling>0)}\n'
                 'fence_t_u_padding_successor legacy_checks=458 extra_checks=241 failures=0\n'
                 'PASSED: fence_t_u_padding_successor\n')
        return console,rows

    def evaluate(self, console, rows):
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=tool.oracle.frozen.FIELDS)
        writer.writeheader()
        hexfields={'pc','insn','rd_wdata','mem_addr','mem_rmask','mem_wmask','mem_wdata'}
        writer.writerows({k:format(v,'x') if k in hexfields else v for k,v in r.items()} for r in rows)
        return tool.evaluate(console,stream.getvalue(),self.metadata,self.blob,self.plan['proof']['sites'])

    def test_complete_three_site_fixture_no_cycle_claim(self):
        result=self.evaluate(*self.fixture())
        self.assertEqual(result['retirement']['capture_stores_checked'],195)
        self.assertFalse(result['cyclequalified']);self.assertFalse(result['application_approval'])

    def test_trap_and_third_store_mutations_rejected(self):
        console,rows=self.fixture()
        trap=next(i for i,r in enumerate(rows) if r['trap'])
        third=int(self.plan['proof']['sites'][2]['resume_pc'],16)
        store=next(i for i,r in enumerate(rows) if r['pc']==third)
        for index,field,value in ((trap,'trap',0),(store,'mem_wdata',0)):
            bad=copy.deepcopy(rows);bad[index][field]=value
            with self.assertRaises(ValueError):self.evaluate(console,bad)

    def test_ceil_uart_mismatch_rejected(self):
        console,rows=self.fixture(100);rows[-1]['rd_wdata']=99
        with self.assertRaises(ValueError):self.evaluate(console,rows)

    def test_full_uart_counts_required(self):
        console,rows=self.fixture()
        with self.assertRaises(ValueError):self.evaluate(console.replace('241','240'),rows)

    def test_terminal_gate_rejects_failure_timeout_identity_and_hash(self):
        outputs={'console':'abc'}
        good=dict(returncode=0,timed_out=False,elapsed_seconds=10,
                  command=self.plan['run']['argv'],cwd=self.plan['run']['cwd'],output_pins=outputs)
        tool.execution_gate(good,self.plan,outputs)
        for key,value in (('returncode',124),('timed_out',True),('command',[]),('cwd','/tmp'),
                          ('output_pins',{}),('elapsed_seconds',900)):
            bad=dict(good);bad[key]=value
            with self.assertRaises(ValueError):tool.execution_gate(bad,self.plan,outputs)

    def test_all151_pin_gate_and_drift_rejection(self):
        pins=self.plan['pins'];tool.check_pins(pins)
        with self.assertRaises(ValueError):tool.check_pins({})
        first=next(iter(pins))
        with patch.object(tool,'sha',side_effect=lambda p:'bad' if p==first else pins[p]):
            with self.assertRaises(ValueError):tool.check_pins(pins)


if __name__=='__main__':unittest.main()
