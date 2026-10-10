import copy
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import qualify_gap113_payload_full8 as q
from ara_verify.vector_commit import ArchActivity, VectorWrite, _deshuffle_byte


def writes(item):
    expected=q.custom_expected(item);result=[]
    for c in range(8):
        for lane in range(4):
            data=bytes(expected[8+c,_deshuffle_byte(lane*8+b,4,2)] for b in range(8))
            result.append(VectorWrite(4,12,1,4,lane,4,q.WORD,2,(8+c)*4,255,int.from_bytes(data,'little'),255))
    return result


class Full8(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native=q.independent_native();cls.view=q.adapter()
        cls.symbols,cls.data,cls.sites=cls.view.elf_view()

    def test_actual_native_and_abi(self):
        self.assertEqual([len(v['result_bits']) for v in self.native],[64,64])
        self.assertEqual(q.descriptor(8),2|(5<<4)|(1<<8)|(2<<12)|(3<<16)|(7<<20))
        self.assertEqual([len(s) for s in self.sites],[8,8])
        with self.assertRaises(ValueError):q.descriptor(7)

    def test_native_scale_bsum_extent_mutations(self):
        w,a,gold=q.recipe.fixture(0);w=w[64:944];a=a[68:2404]
        for target,offset in [('a',0),('a',2080),('w',108)]:
            changed=bytearray(a if target=='a' else w);changed[offset]^=1
            with self.subTest(target=target,offset=offset),self.assertRaises(ValueError):
                q.unpack(w,changed) if target=='a' else q.unpack(changed,a)
        for weight,activation in [(w[:-1],a),(w,a[:-1])]:
            with self.assertRaises(ValueError):q.unpack(weight,activation)

    def test_frozen_gold_templates_reject(self):
        original=Path.read_bytes
        for filename in ('templates.log','gold0.json','gold1.json'):
            def changed(path):
                raw=original(path)
                if path.name==filename:
                    if path.suffix=='.json':
                        value=json.loads(raw);value['bits'][-1]^=1;return json.dumps(value).encode()
                    raw=bytearray(raw);raw[-1]^=1;return bytes(raw)
                return raw
            with patch.object(Path,'read_bytes',changed),self.assertRaises(ValueError):q.independent_native()

    def test_full_write_and_masks(self):
        for item in self.native:
            a=ArchActivity(q.WORD,1,1,True,8,2,256,0,writes(item))
            q.activity_bytes(a,q.custom_expected(item),10,20,custom=True)
            self.assertEqual(len(q.custom_expected(item)),256)

    def test_write_corruption_lifecycle_shape_reject(self):
        item=self.native[0];a=ArchActivity(q.WORD,1,1,True,8,2,256,0,writes(item))
        for mutation in (dict(data=a.writes[0].data^1),dict(source=0),dict(known_be=0),
                         dict(cycle=21),dict(eew=1),dict(addr=60),dict(be=0),dict(vid=2),dict(arch_seq=99)):
            bad=copy.deepcopy(a);bad.writes[0]=replace(bad.writes[0],**mutation)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                q.activity_bytes(bad,q.custom_expected(item),10,20,custom=True)
        for field,value in [('vl',160),('vd',16),('instruction',0x08b5045b)]:
            bad=copy.deepcopy(a);setattr(bad,field,value)
            with self.assertRaises(ValueError):q.activity_bytes(bad,q.custom_expected(item),10,20,custom=True)
        for values in (a.writes[:-1],a.writes+[a.writes[0]]):
            bad=copy.deepcopy(a);bad.writes=values
            with self.assertRaises(ValueError):q.activity_bytes(bad,q.custom_expected(item),10,20,custom=True)

    def readbacks(self):
        expected=q.regions(0,self.symbols,self.data,self.native);rows=[]
        for name,blob in expected.items():
            for offset in range(0,len(blob),8):
                rows.append(dict(event='retire',cycle='10',pc='80000300',mem_addr=hex(self.symbols[name][0]+offset),
                    mem_rmask='ff',mem_wmask='0',insn='00003283',rd='5',trap='0',
                    rd_wdata=hex(int.from_bytes(blob[offset:offset+8],'little'))))
        return rows,expected

    def test_full_regions_and_preserved_vrf(self):
        rows,expected=self.readbacks()
        self.assertEqual(q.inherited.readback(rows,0,20,self.symbols,expected),
            dict(initial=4224,actual=4224,weights=1024,activation=2496,descriptor_packet=144,csr_packet=160))
        for phase in (0,1):
            regions=q.regions(phase,self.symbols,self.data,self.native)
            for reg in range(32):
                for byte in range(128):
                    if (reg,byte) not in q.custom_expected(self.native[phase]):
                        self.assertEqual(regions['actual'][64+128*reg+byte],regions['initial'][64+128*reg+byte])

    def test_all_region_corruption_missing_unknown_reject(self):
        rows,expected=self.readbacks()
        for name,blob in expected.items():
            bad=copy.deepcopy(rows);address=self.symbols[name][0]+len(blob)-8
            row=next(r for r in bad if int(r['mem_addr'],16)==address);row['rd_wdata']=hex(int(row['rd_wdata'],16)^1)
            with self.assertRaises(ValueError):q.inherited.readback(bad,0,20,self.symbols,expected)
        with self.assertRaises(ValueError):q.inherited.readback(rows[:-1],0,20,self.symbols,expected)
        rows[0]['rd_wdata']='xxxxxxxx'
        with self.assertRaises(ValueError):q.inherited.readback(rows,0,20,self.symbols,expected)

    def text(self):
        return '\n'.join(['GAP110 command=0 checks=17 errors=0','GAP110 command=1 checks=17 errors=0',
            'GAP110 inspected vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24',
            'PASSED: qbs_gap110_q3_r4_tail checks=41 errors=0',
            'PASSED: qbs_gap113_payload_full8 inherited_checks=41 errors=0','Core Test *** SUCCESS ***',
            '[ARA_CONTRACT] requests=100 responses=100 exceptions=0 mmu_request_cycles=0 '
            'protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'])+'\n'

    def check_log(self,text):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'log';p.write_text(text);return q.software(p)

    def test_software_terminal(self):self.check_log(self.text())

    def test_error_exception_incomplete_terminal_reject(self):
        original=self.text()
        for text in (original.replace('exceptions=0','exceptions=1'),original.replace('protocol_errors=0','protocol_errors=1'),
                     original.replace('outstanding=0','outstanding=1'),original.replace('responses=100','responses=99'),
                     original.replace('errors=0','errors=1'),original.replace('inherited_checks=41','inherited_checks=40'),
                     original+'Core Test *** SUCCESS ***\n',original+'Fatal: tohost=3\n'):
            with self.assertRaises(ValueError):self.check_log(text)

    def test_report_only_adapter_counts(self):
        audit=dict(bindings=[dict(software_vl=8,backend_vl=160,native_active_write_bytes=160) for _ in (0,1)],
                   custom_write_bytes=240,full_vrf_bytes=8192)
        fake=type('Fake',(),{'runtime':staticmethod(lambda *args:copy.deepcopy(audit))})()
        result=q.runtime(fake,self.symbols,self.data,self.sites,self.native)
        self.assertEqual(result['custom_write_bytes'],512)
        self.assertEqual(result['custom_preserved_vrf_bytes'],7680)
        self.assertTrue(all(b['backend_vl']==256 for b in result['bindings']))
        audit['custom_write_bytes']=1
        with self.assertRaises(ValueError):q.runtime(fake,self.symbols,self.data,self.sites,self.native)

    def test_private_bindings_and_pin_drift(self):
        self.assertEqual(self.view.runtime.__globals__['activity_bytes'],q.activity_bytes)
        self.assertEqual(self.view.runtime.__globals__['regions'],q.regions)
        self.assertEqual(q.inherited.WORD,0x08b5045b)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'pin';p.write_text('old');pins={str(p):q.life.digest(p)};p.write_text('new')
            with self.assertRaises(ValueError):q.life.check(pins)


if __name__=='__main__':unittest.main()
