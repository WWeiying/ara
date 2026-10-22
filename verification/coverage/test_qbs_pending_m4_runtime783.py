"""Real ELF/regions and strict native/terminal/corruption/worker negative tests; no EDA."""
import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import collect_qbs_pending_m4_783 as c
import execute_qbs_pending_m4_783 as worker


class RuntimeTests(unittest.TestCase):
    def setUp(self):self.symbols,self.data,self.sites,self.items=c.elf_view()

    def test_actual_elf18_activities(self):
        self.assertEqual([len(s) for s in self.sites],[8,8])
        self.assertEqual([len(i['result_bits']) for i in self.items],[32,32])
        self.assertEqual(c.runner.life.digest(c.runner.ELF),c.runner.ELF_SHA)

    def test_full_regions_both_checkpoints(self):
        for phase in (0,1):
            expected=c.regions(phase,self.symbols,self.data,self.items)
            self.assertEqual(len(expected['frame'+str(phase)]),4224)
            self.assertEqual(len(expected['csr'+str(phase)]),160)
            self.assertEqual(len(expected['desc'+str(phase)]),144)
            self.assertEqual(sum(len(v) for k,v in expected.items() if k.startswith(('weight','activation'))),12416)
            desc=expected['desc'+str(phase)];header=struct.unpack_from('<Q',desc,64)[0]
            self.assertEqual(header&15,2);self.assertEqual(header>>4&15,7 if phase==0 else 2)
            self.assertEqual(header>>8&15,1)

    def test_integer_gold_corruption(self):
        fixtures=c.recipe.fixture();mutated=copy.deepcopy(fixtures)
        w,a,g,d=mutated[1];g=bytearray(g);g[1024]^=1;mutated[1]=(w,a,bytes(g),d)
        with patch.object(c.recipe,'fixture',return_value=mutated):
            with self.assertRaises(ValueError):c.elf_view()

    def test_source_and_tail_corruptions(self):
        fixtures=c.recipe.fixture()
        for which in (0,1,2):
            mutated=copy.deepcopy(fixtures);entry=list(mutated[1]);value=bytearray(entry[which]);value[-1]^=1;entry[which]=bytes(value);mutated[1]=tuple(entry)
            with patch.object(c.recipe,'fixture',return_value=mutated):
                with self.assertRaises(ValueError):c.elf_view()

    def test_missing_checkpoint_objects(self):
        with self.assertRaises(ValueError):c.regions(2,self.symbols,self.data,self.items)
        with self.assertRaises(ValueError):c.regions(0,dict(self.symbols,weight0=(0,1)),self.data,self.items)

    def test_software_labels_and_diagnostics(self):
        source=(c.life.OUT/'qbs-k2-row-pending-old-image782-agent-20261008-01/run.vcs.log').read_text()
        source=source.replace('QBS_PENDING checks=6 errors=0',
            'QBS_TWO_PHASE phase=0 checks=6 errors=0\nQBS_TWO_PHASE phase=1 checks=12 errors=0')
        source=source.replace('PASSED: qbs_k2_row_pending781 commands=1 errors=0',
            'PASSED: qbs_pending_two_phase783 commands=2 errors=0')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.log';path.write_text(source)
            self.assertGreater(c.software(path)['requests'],0)
            for bad in (source.replace('phase=1 checks=12 errors=0','phase=1 checks=12 errors=1'),
                source+'\nFatal: wrong\n',source.replace('UVM_ERROR :    0','UVM_ERROR :    1')):
                if bad==source:continue
                path.write_text(bad)
                with self.assertRaises(ValueError):c.software(path)

    def test_native_expected_full512(self):
        for item in self.items:
            expected=c.core.custom_expected(item);self.assertEqual(len(expected),512)
            self.assertTrue(all(expected[(r,b)]==0 for r in range(8,12) for b in range(32,128)))
        bad=dict(self.items[0],result_bits=self.items[0]['result_bits'][:-1])
        with self.assertRaises(ValueError):c.core.custom_expected(bad)

    def test_missing_source_readback_and_corruption(self):
        expected={'weight0':bytes(8)};symbols={'weight0':(0x80001000,8)}
        with self.assertRaises(ValueError):c.core.matrix.readback([],0,10,symbols,expected,lambda p,n:b'')
        row=dict(event='retire',cycle='1',mem_addr='80001000',mem_rmask='ff',insn='0002b383',rd='7',trap='0',rd_wdata='1',pc='80000000')
        with self.assertRaises(ValueError):c.core.matrix.readback([row],0,10,symbols,expected,lambda p,n:bytes.fromhex('83b30200'))

    def test_valid_source_readback_actual_scalar_decoder(self):
        row=dict(event='retire',cycle='1',mem_addr='80001000',mem_rmask='ff',insn='0002b383',rd='7',trap='0',rd_wdata='0',pc='80000000')
        got=c.core.matrix.readback([row],0,10,{'weight0':(0x80001000,8)},{'weight0':bytes(8)},lambda p,n:bytes.fromhex('83b30200'))
        self.assertEqual(got['weight0'],8)

    def test_actual_error_guard_not_source_echo(self):
        pattern=r'^\s*(?:QBS_TWO_PHASE_PROBE_REJECT\b|UCLI_ERROR\b|Error-)'
        self.assertIsNone(c.re.search(pattern,'puts stderr "QBS_TWO_PHASE_PROBE_REJECT $failure"',c.re.M))
        self.assertIsNotNone(c.re.search(pattern,' QBS_TWO_PHASE_PROBE_REJECT failed',c.re.M))

    def test_parent_authorization_before_prepare(self):
        with patch.object(sys,'argv',['worker','run','--output',str(c.life.OUT/'not-created'),'--prepared-seal','a'*64]),patch.object(worker,'prepare',side_effect=AssertionError('must not prepare')):
            with self.assertRaises(ValueError):worker.main()

    def test_native_terminal_wrong_word_vl(self):
        class Activity:
            instruction=0x0eb5045b;vd=8;vl=128;writes=[]
        with patch.object(c.core.native.support,'activity_bytes'):
            with self.assertRaises(ValueError):c.core.activity_bytes(Activity(),c.core.custom_expected(self.items[0]),0,1,custom=True)


if __name__=='__main__':unittest.main()
