"""Host checks for scope, source preservation and the measured reference gate."""
import json
from pathlib import Path
import unittest

import adapter


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.build = adapter.HERE / 'measurement01/build'

    def test_original_sources_unchanged(self):
        original = self.build / 'prepared' / adapter.NAME / 'original'
        for name, digest in adapter.PINS.items():
            self.assertEqual(adapter.prepare.sha(original / name), digest)
            self.assertEqual((original / name).read_bytes(),
                             (adapter.SOURCE / name).read_bytes())

    def test_wrapper_only_adaptation(self):
        source = (adapter.SOURCE / 'scenario.c').read_text()
        case = (self.build / 'prepared' / adapter.NAME / 'case.c').read_text()
        self.assertEqual(case, adapter.prepare.adapt(source, adapter.NAME))
        body_start = source.index('    unsigned cap=capacity()')
        body_end = source.index('    syscall3(94,errors ? 1:0,0,0);')
        body = source[body_start:body_end].replace(
            'syscall3(94,2,0,0);for(;;){}', 'return 2;').replace(
            'syscall3(29,1,0x5409,1);',
            '/* Linux TIOCOUTQ omitted; timing is not equivalent. */')
        self.assertIn(body, case)

    def test_original_oracle_tail_and_guards(self):
        source = (adapter.SOURCE / 'scenario.c').read_text()
        self.assertIn('seed!=0 || op!=2 || l!=5 || mode!=0', source)
        self.assertIn('output+1,mask,vl,cap', source)
        self.assertIn('i<bytes;++i)if(output[i+1]!=expected[i])', source)
        self.assertIn('output[0]!=0x5b || output[bytes+1]!=0x5b', source)
        data = bytes(((i * 73) ^ 0x85) & 255 for i in range(128))
        self.assertEqual(int.from_bytes(data[-2:], 'little'), 0xb26b)

    def test_spike_gate_and_program_pins(self):
        ref = json.loads((self.build / 'reference_checked.json').read_text())
        self.assertEqual(ref['status'], 'PASS')
        self.assertEqual(ref['returncode'], 0)
        self.assertIn(adapter.MARKER, (self.build / 'spike_checked.log').read_text())
        for backend, record in ref['programs'].items():
            self.assertEqual(adapter.prepare.sha(
                self.build / backend / (adapter.NAME + '.elf')), record['elf_sha256'])
        adapter.prepare.check(self.build / 'prepared')

    def test_scope_and_bounded_profile(self):
        with self.assertRaises(ValueError):
            adapter.inside(Path('/tmp/escape'))
        self.assertEqual(len(adapter.profile()), len(set(adapter.profile())))
        self.assertIn(adapter.ARA + '.i_dispatcher.legal_widen_overlap', adapter.profile())
        self.assertIn(adapter.ARA + '.i_dispatcher.eew_q[25]', adapter.profile())
        self.assertIn(adapter.ARA + '.i_dispatcher.backend_valid', adapter.profile())
        self.assertIn('final03/campaign/image', str(adapter.IMAGE))


if __name__ == '__main__':
    unittest.main()
