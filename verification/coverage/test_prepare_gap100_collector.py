import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_gap100_collector as m


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.ref = json.loads((m.ledger.REFERENCE / 'reference-result.json').read_bytes())

    def test_actual_reference(self):
        m.validate_reference(self.ref)

    def test_actual_zero_contract_keeps_inapplicable_activity_diagnostics(self):
        checks = json.loads((m.OUT / 'gap100-runtime-diagnostic-713-20261006-02/diagnostic.json').read_bytes())
        checks['scalar_comparison_qualified'] = True
        m.validate_runtime(checks)
        checks['contract']['counts']['exceptions'] = 1
        with self.assertRaises(ValueError):
            m.validate_runtime(checks)

    def test_ledger_json_keys_exact(self):
        actual = {'ledger': [{'cause_reads': {0x342: [11]}}]}
        proof = json.loads(json.dumps(actual))
        m.verify_ledger(actual, proof)
        proof['ledger'][0]['cause_reads'][str(0x342)] = [9]
        with self.assertRaises(ValueError):
            m.verify_ledger(actual, proof)

    def test_partial_or_unknown_rejected(self):
        for key, value in [('status', 'PREFIX_MATCH'), ('skipped_unobservable_register_values', 1),
                           ('mismatch', {'reason': 'different'}), ('matched_instructions', 6829)]:
            ref = copy.deepcopy(self.ref)
            ref['scalar'][key] = value
            with self.assertRaises(ValueError):
                m.validate_reference(ref)

    def test_reference_identity_rejected(self):
        for key, value in [('input_elf_sha256', '0' * 64), ('normalization_performed', True),
                           ('coverage_admitted', True), ('RTL_reexecuted', True)]:
            ref = copy.deepcopy(self.ref)
            ref[key] = value
            with self.assertRaises(ValueError):
                m.validate_reference(ref)

    def test_actual714_membership(self):
        old = json.loads((m.BASE / 'combined-bits.json').read_bytes())
        lines = (m.BASE / 'combined-inputs.txt').read_text().splitlines()
        prior = json.loads(m.IDENTITIES.read_bytes())
        identities = prior['baseline_identity'] + [dict(vdb=c['vdb'], elf_sha256=c['elf']['sha256'])
                                                   for c in prior['cases']]
        cases = json.loads((m.BASE / 'admissions.json').read_bytes())['cases']
        identities += [dict(vdb=c['vdb'], elf_sha256=c['elf']['sha256']) for c in cases]
        m.validate_membership(old, lines, identities, str(m.runtime.RUN / 'code.vdb'), m.runner.ELF_SEAL)
        for vdb, elf in [(old['tests'][0], m.runner.ELF_SEAL),
                         (str(m.runtime.RUN / 'code.vdb'), identities[0]['elf_sha256'])]:
            with self.assertRaises(ValueError):
                m.validate_membership(old, lines, identities, vdb, elf)
        with self.assertRaises(ValueError):
            m.validate_membership(old, lines, identities[::-1], str(m.runtime.RUN / 'code.vdb'), m.runner.ELF_SEAL)

    def test_expected_hash_not_resampled(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'pin'
            m.save(p, 'old')
            with self.assertRaises(ValueError):
                m.life.read_bound(p, '0' * 64)

    def test_text_output_is_plain_not_json_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'inputs.txt'
            m.save(p, '/design\n/test\n')
            self.assertEqual(p.read_text().splitlines(), ['/design', '/test'])
            with self.assertRaises(FileExistsError):
                m.save(p, 'replacement')

    def test_shape_drift_rejected(self):
        original = {'targets': [dict(metric='cond', scope='s', point={'raw_index': 0})]}
        a = {'metrics': {'cond': {'s': dict(width=1, checksum='x', bits='0x0')}}}
        b = {'metrics': {'cond': {'s': dict(width=2, checksum='x', bits='0x2')}}}
        with patch.object(m.runner, 'validate_targets'):
            with self.assertRaises(ValueError):
                m.target_rebind(a, b, b, original)

    def test_target_bit_direction_and_previous_hit_preserved(self):
        original = {'targets': [dict(metric='cond', scope='s', point={'raw_index': 0})]}
        a = {'metrics': {'cond': {'s': dict(width=3, checksum='x', bits='0x4')}}}
        with patch.object(m.runner, 'validate_targets'):
            result = m.target_rebind(a, a, a, original)
        self.assertTrue(result[0]['hit_before714'])


if __name__ == '__main__':
    unittest.main()
