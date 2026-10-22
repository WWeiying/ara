"""All predecessor gates plus cached-word equivalence and measured reduction."""
import json
import os
from pathlib import Path
import unittest

import build_narrow_reject_r1_cached_preflight as p
import test_narrow_reject_r1_preflight as predecessor


class CachedStaticTests(predecessor.StaticTests):
    def test_independent_cached_word_equivalence(self):
        gold=[[int.from_bytes(p.original.expected_register(r)[w*8:w*8+8],'little')
               for w in range(16)] for r in range(32)]
        recovery=int.from_bytes(bytes((0x56,0x63,0x70,0x7d)),'little')
        for phase in range(26):
            for r in range(32):
                for w in range(16):
                    expected=gold[r][w]
                    if phase==25 and r==16 and w==0:
                        expected=(expected&0xffffffff00000000)|recovery
                    self.assertEqual(expected,int.from_bytes(
                        p.original.expected_register(r,phase==25)[w*8:w*8+8],'little'))

    def test_gold_has_no_snapshot_source(self):
        source=p.APP.read_text()
        self.assertIn('r1_gold[32][16]',source)
        self.assertIn('r1_dump_word(0, r, w + 1)',source)
        self.assertNotIn('gnr_dump',source)
        self.assertIn('#include "vnarrow_reject_r1_matrix.c"',source)

    def test_no_reduction_rejected(self):
        old={'reference_counts':{'matched_instructions':1049731}}
        for count in (0,1049731,1049732):
            with self.assertRaises(ValueError):p.instruction_reduction({'matched_instructions':count},old)

    def test_measured_reduction_arithmetic(self):
        result=p.instruction_reduction({'matched_instructions':500000},
                                      {'reference_counts':{'matched_instructions':1049731}})
        self.assertEqual(result['fewer'],549731)
        self.assertIsNone(result['VCS_CPU_seconds_measured'])

    def test_original_seal_preserved(self):
        p.life.read_bound(p.OLD/'preflight-manifest.json',p.OLD_SEAL)


@unittest.skipUnless(os.environ.get('R1_CACHED_PREFLIGHT'),'Set R1_CACHED_PREFLIGHT for actual cached fixture')
class CachedActualTests(predecessor.ActualTests):
    __unittest_skip__ = False

    @classmethod
    def setUpClass(cls):
        cls.out=Path(os.environ['R1_CACHED_PREFLIGHT']).absolute()
        cls.pre=json.loads((cls.out/'preflight-manifest.json').read_text())
        cls.commits=p.original.shared.parse_spike_commits(cls.out/'spike.trace')
        cls.symbols=cls.pre['symbols'];cls.trace=(cls.out/'spike.trace').read_text()

    def test_actual_instruction_reduction(self):
        old=p.life.read_bound(p.OLD/'preflight-manifest.json',p.OLD_SEAL)
        actual=p.original.strict.reference_counts(self.commits,self.symbols)
        self.assertEqual(p.instruction_reduction(actual,old),self.pre['instruction_reduction'])
        self.assertLess(actual['matched_instructions'],1049731)

    def test_all_functional_oracle_counts_unchanged(self):
        old=p.life.read_bound(p.OLD/'preflight-manifest.json',p.OLD_SEAL)
        before={k:v for k,v in old['validation'].items() if k!='ordered_fault_pcs'}
        after={k:v for k,v in self.pre['validation'].items() if k!='ordered_fault_pcs'}
        self.assertEqual(before,after)


if __name__=='__main__':unittest.main()
