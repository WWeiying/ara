"""Exact730/PureWAR731 gates; no admission, EDA, or VDB collection."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import admit_pure_war_offline731 as h


class AdmissionTests(unittest.TestCase):
    def test_actual_diagnostic_contract(self):
        h.candidate_contract(json.loads((h.CANDIDATE / 'diagnostic.json').read_bytes()))

    def test_diagnostic_negative_mutations(self):
        record = json.loads((h.CANDIDATE / 'diagnostic.json').read_bytes())
        for key, value in [('baseline_count', 729), ('baseline_seal', 'a' * 64),
                           ('qualification_seal', 'a' * 64), ('targets_hit_single', 3),
                           ('new_targets', 3), ('positive_raw_gain', False),
                           ('coverage_admitted', True), ('rtl_changed', True),
                           ('native_DVE_selector_binding', True), ('source_lifetime_stall_proven', True),
                           ('raw_delta', dict(line=1, cond=4, branch=0, fsm=0))]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.candidate_contract(dict(record, **{key: value}))

    def test_seal_drift_before_read(self):
        with patch.object(h.life, 'read_bound', side_effect=AssertionError('must not read')):
            for args in [('a' * 64, h.QUAL_SEAL, h.CANDIDATE_SEAL),
                         (h.BASE_SEAL, 'a' * 64, h.CANDIDATE_SEAL),
                         (h.BASE_SEAL, h.QUAL_SEAL, 'a' * 64)]:
                with self.assertRaises(ValueError): h.evaluate(*args)

    def test_exact_gain_and_foreign_gain(self):
        targets = [dict(scope=f'lane{i}') for i in range(4)]
        before = dict(metrics={'cond': {t['scope']: dict(width=1060, bits='0x0') for t in targets}})
        after = copy.deepcopy(before)
        for row in after['metrics']['cond'].values(): row['bits'] = '0x1'
        h.exact_gain(before, after, targets)
        after['metrics']['cond']['lane0']['bits'] = '0x3'
        with self.assertRaises(ValueError): h.exact_gain(before, after, targets)

    def test_missing_target_gain(self):
        targets = [dict(scope=f'lane{i}') for i in range(4)]
        before = dict(metrics={'cond': {t['scope']: dict(width=1060, bits='0x0') for t in targets}})
        after = copy.deepcopy(before)
        with self.assertRaises(ValueError): h.exact_gain(before, after, targets)

    def test_recursive_elf_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            elf = Path(directory) / 'input.elf'; ledger = Path(directory) / 'evidence-pins.json'
            with elf.open('x') as stream: stream.write('same-ELF')
            elfseal = h.life.digest(elf)
            with ledger.open('x') as stream: json.dump({str(elf): elfseal}, stream)
            pins = {str(ledger): h.life.digest(ledger)}
            self.assertEqual(h.evidence_elf_hashes(pins), {elfseal})
            with elf.open('w') as stream: stream.write('drift')
            with self.assertRaises(ValueError): h.evidence_elf_hashes(pins)

    def test_pin_ledger_drift(self):
        with self.assertRaises(ValueError):
            h.evidence_elf_hashes({str(h.BASE / 'evidence-pins.json'): 'a' * 64})

    def test_nonledger_pin_checked_by_caller(self):
        pins = {str(h.raw.QUAL): 'a' * 64}
        self.assertEqual(h.evidence_elf_hashes(pins), set())
        with self.assertRaises(ValueError): h.life.check(pins)

    def test_actual_evaluate_no_recollection(self):
        with patch.object(h.raw.bitmap, 'collect', side_effect=AssertionError('no recollection')):
            outputs, text = h.evaluate(h.BASE_SEAL, h.QUAL_SEAL, h.CANDIDATE_SEAL)
        self.assertEqual(outputs['status.json']['aggregate_passed'], 731)
        self.assertEqual(outputs['status.json']['raw_delta'], h.EXPECTED_DELTA)
        tests = outputs['combined-bits.json']['tests']
        self.assertEqual(len(tests), 731)
        self.assertEqual(len(set(tests)), 731)
        self.assertEqual(text.splitlines(), [str(h.raw.DESIGN), *tests])
        self.assertFalse(outputs['status.json']['source_lifetime_stall_proven'])


if __name__ == '__main__': unittest.main()
