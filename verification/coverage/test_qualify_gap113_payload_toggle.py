import copy
import json
from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch
import qualify_gap113_payload_toggle as q
from test_qualify_gap110_native_v2 import custom_writes
from ara_verify.vector_commit import ArchActivity


class Tests(unittest.TestCase):
    def setUp(self):
        self.native=q.independent_native();self.view=q.adapter()
        self.symbols,self.data,self.sites=self.view.elf_view()

    def test_independent_gold_and_new_abi_binding(self):
        self.assertEqual([i['integer_dots'][:4] for i in self.native],
                         [[-11904,12288,15872,-16384]]*2)
        for phase in (0,1):
            self.assertEqual(len(self.sites[phase]),8)
            regions=q.regions(phase,self.symbols,self.data,self.native)
            self.assertEqual(sum(map(len,regions.values())),12272)
            self.assertEqual(self.view.abi_descriptor_header((7,5)[phase]),
                             2|(5<<4)|(1<<8)|(2<<12)|(3<<16)|(((7,5)[phase]-1)<<20))

    def test_frozen_gold_and_templates_negative(self):
        original=Path.read_bytes
        for filename in ('templates.log','gold0.json','gold1.json'):
            def changed(path):
                raw=original(path)
                if path.name==filename:
                    if path.suffix=='.json':
                        value=json.loads(raw);value['bits'][0]^=1;return json.dumps(value).encode()
                    raw=bytearray(raw);raw[-1]^=1;return bytes(raw)
                return raw
            with patch.object(Path,'read_bytes',changed):
                with self.assertRaises(ValueError):q.independent_native()

    def readbacks(self):
        expected=q.regions(0,self.symbols,self.data,self.native);rows=[]
        for name,blob in expected.items():
            for offset in range(0,len(blob),8):
                rows.append(dict(event='retire',cycle='10',pc='80000300',mem_addr=hex(self.symbols[name][0]+offset),
                    mem_rmask='ff',mem_wmask='0',insn='00003283',rd='5',trap='0',
                    rd_wdata=hex(int.from_bytes(blob[offset:offset+8],'little'))))
        return rows,expected

    def test_full_vrf_source_guard_csr_readbacks(self):
        rows,expected=self.readbacks()
        self.assertEqual(q.inherited.readback(rows,0,20,self.symbols,expected),
            dict(initial=4224,actual=4224,weights=1024,activation=2496,descriptor_packet=144,csr_packet=160))

    def test_each_region_corruption_missing_or_unknown_rejected(self):
        rows,expected=self.readbacks()
        for name,blob in expected.items():
            mutated=copy.deepcopy(rows);address=self.symbols[name][0]+len(blob)-8
            row=next(r for r in mutated if int(r['mem_addr'],16)==address);row['rd_wdata']=hex(int(row['rd_wdata'],16)^1)
            with self.assertRaises(ValueError):q.inherited.readback(mutated,0,20,self.symbols,expected)
        with self.assertRaises(ValueError):q.inherited.readback(rows[:-1],0,20,self.symbols,expected)
        rows[0]['rd_wdata']='xxxxxxxx'
        with self.assertRaises(ValueError):q.inherited.readback(rows,0,20,self.symbols,expected)

    def test_custom_write_gold_masks_and_tail(self):
        for item in self.native:
            a=ArchActivity(q.inherited.WORD,1,1,True,8,2,160,0,custom_writes(item))
            q.inherited.activity_bytes(a,q.inherited.custom_expected(item),10,20,custom=True)
            for mutation in (dict(data=a.writes[0].data^1),dict(source=0),dict(known_be=0),
                             dict(cycle=21),dict(eew=1),dict(addr=60),dict(be=0)):
                b=copy.deepcopy(a);b.writes[0]=replace(b.writes[0],**mutation)
                with self.assertRaises(ValueError):q.inherited.activity_bytes(b,q.inherited.custom_expected(item),10,20,custom=True)
            for writes in (a.writes[:-1],a.writes+[a.writes[0]]):
                b=copy.deepcopy(a);b.writes=writes
                with self.assertRaises(ValueError):q.inherited.activity_bytes(b,q.inherited.custom_expected(item),10,20,custom=True)

    def text(self):
        return '\n'.join(['GAP110 command=0 checks=17 errors=0','GAP110 command=1 checks=17 errors=0',
            'GAP110 inspected vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24',
            'PASSED: qbs_gap110_q3_r4_tail checks=41 errors=0',
            'PASSED: qbs_gap113_payload_toggle inherited_checks=41 errors=0','Core Test *** SUCCESS ***',
            '[ARA_CONTRACT] requests=100 responses=100 exceptions=0 mmu_request_cycles=0 '
            'protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'])+'\n'

    def software_check(self,text):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'log';log.write_text(text);return q.software(log)

    def test_terminal_contract_and_distinct_check(self):self.software_check(self.text())

    def test_terminal_errors_extra_exception_protocol_and_missing_checks(self):
        original=self.text()
        for text in (original.replace('exceptions=0','exceptions=1'),original.replace('protocol_errors=0','protocol_errors=1'),
            original.replace('outstanding=0','outstanding=1'),original.replace('responses=100','responses=99'),
            original.replace('errors=0','errors=1'),original.replace('inherited_checks=41','inherited_checks=40'),
            original+ 'Core Test *** SUCCESS ***\n',original+'Fatal: tohost=3\n'):
            with self.assertRaises(ValueError):self.software_check(text)

    def test_gain_exact_scope_and_no_gain_truthful(self):
        evidence=json.loads(q.recipe.EVIDENCE.read_bytes());sample=copy.deepcopy(evidence['metrics'])
        self.assertEqual(q.scoped_gain(sample,evidence)['total_new_serialized_toggle_positions'],0)
        point=q.recipe.target(evidence)['serialized_zero_coordinates'][0];row=sample[q.recipe.SCOPE]
        row['bits']=hex(int(row['bits'],16)|(1<<(row['width']-1-point)))
        gain=q.scoped_gain(sample,evidence)
        self.assertEqual(gain['total_new_serialized_toggle_positions'],1)
        self.assertEqual(gain['primary_target_hits'],[point]);self.assertFalse(gain['direction_binding_verified'])
        for key,value in (('checksum','999'),('width',66339)):
            broken=copy.deepcopy(sample);broken[q.recipe.SCOPE][key]=value
            with self.assertRaises(ValueError):q.scoped_gain(broken,evidence)
        del sample[q.recipe.SCOPE]
        with self.assertRaises(ValueError):q.scoped_gain(sample,evidence)

    def test_pin_drift_and_wrong_run_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pin';path.write_text('one');pins={str(path):q.life.digest(path)}
            path.write_text('two')
            with self.assertRaises(ValueError):q.life.check(pins)
        with self.assertRaises(ValueError):q.prepare(q.RUN.with_name('other'),'x'*64)

    def test_private_adapter_does_not_mutate_inherited_globals(self):
        self.assertNotEqual(q.inherited.runner.PRE,q.runner.PRE)
        self.assertEqual(self.view.runner.PRE,q.runner.PRE)
        self.assertEqual(self.view.runtime.__globals__['regions'],q.regions)
        self.assertEqual(self.view.runtime.__globals__['software'],q.software)


if __name__=='__main__':unittest.main()
