"""Legal M4 descriptor audit, packed gold and actual positive/rejection fixtures."""
import json
import os
from pathlib import Path
import subprocess
import unittest

import build_qbs_pending_two_phase_m4_783 as b


class SourceTests(unittest.TestCase):
    def test_descriptor_chain_complete(self):
        proof=b.static()
        self.assertEqual(len(proof['validation_order']),17)
        self.assertEqual(set(proof['validation_order']),set(proof['validation_witnesses']))
        self.assertEqual([p['m'] for p in proof['phases']],[4,4])
        self.assertIn('withdrawn',proof['explicit_retraction'])

    def test_legal_mapping_exact_unique(self):
        proof=b.static();cs=proof['remaining_coordinates']
        self.assertEqual(sum(map(len,cs.values())),proof['legal_mapping_upper_bound'])
        self.assertTrue(all(len(v)==len(set(v)) for v in cs.values()))
        self.assertGreater(proof['legal_mapping_upper_bound'],214)

    def test_source_gold_m4_tail_and_unchanged_phase0(self):
        first,second=b.fixture();self.assertEqual(first,b.frozen.old.fixture())
        w,a,gold,values=second
        self.assertEqual(len(values),32)
        for ctx in range(4):self.assertEqual(gold[1024+128*ctx+32:1024+128*(ctx+1)],bytes(96))
        seed=b.frozen.old.seed_bytes()
        self.assertEqual(gold[:1024],seed[:1024]);self.assertEqual(gold[1536:],seed[1536:])
        self.assertEqual(a[76+2336:],bytes([0x5a])*(len(a)-76-2336))

    def test_q6_decoding_and_offsets(self):
        w,a,_,_=b.fixture()[1]
        for row in range(8):
            for k in range(2):
                start=74+(2*row+k)*210;values,scales=b.frozen.decode_q6(w[start:start+210])
                self.assertEqual(values,[b.frozen.q6_value(row,k,i) for i in range(256)])
                self.assertEqual(scales,[b.frozen.q6_scale(row,k,g) for g in range(16)])
        self.assertIn('gold1,4,3360,2336,3520,4864,76',b.header())


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('QBS_M4_PREFLIGHT')
        if not value:raise unittest.SkipTest('Set QBS_M4_PREFLIGHT to actual immutable preflight')
        cls.out=Path(value).resolve();cls.record=json.loads((cls.out/'preflight-manifest.json').read_text())

    def test_pins_elf_sites(self):
        b.common.verify(self.record['input_pins']);b.common.verify(self.record['output_pins'])
        self.assertEqual(b.common.sha(Path(self.record['binary'])),self.record['binary_sha256'])
        self.assertEqual([s['word'] for s in self.record['sites']],list(b.WORDS))
        self.assertEqual([p['m'] for p in self.record['phases']],[4,4])

    def test_actual_valid_positive(self):
        p=subprocess.run([self.out/'host'],capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0);self.assertIn(b'phase=1 checks=14 errors=0',p.stdout)
        self.assertEqual(self.record['full_vrf_checkpoint_bytes'],[4096,4096])

    def test_actual_invalid_m8_row_rejected_without_writes(self):
        p=b.subprocess_run(self.out/'host')
        self.assertEqual(p.returncode,0)
        self.assertRegex(p.stdout.decode(),r'INVALID_M8_ROW status=\d+ untouched=1')

    def test_actual_all_corruptions(self):
        for phase in range(2):
            for mutation in b.MUTATIONS:
                with self.subTest(phase=phase,mutation=mutation):
                    p=subprocess.run([self.out/'host',mutation,str(phase)],capture_output=True,timeout=10)
                    self.assertEqual(p.returncode,1);self.assertIn(b'FAILED:',p.stdout)
        self.assertEqual(self.record['host_negative_tests'],19)


if __name__=='__main__':unittest.main()
