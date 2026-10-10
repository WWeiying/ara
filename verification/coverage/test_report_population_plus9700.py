import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import report_population_plus9700 as m


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = (m.OUT / 'current-population780-compact-prepared-agent-20261008-01/combined.el').read_text()
        cls.config = json.loads((m.LARGE[1] / 'config.json').read_bytes())
        cls.native = (m.LARGE[1] / 'second.el').read_text()
        cls.additions = [((f[1] / 'second.el').read_text(), f[5]) for f in m.FAMILIES]

    def test_actual9440_qualification_full_complement_and_native_reload(self):
        text, count, pins = m.qualification(m.stable.Reader(), m.LARGE)
        self.assertEqual(text, self.native)
        self.assertEqual(count, 9440)
        self.assertIn(str(m.LARGE[1] / 'terminal.json'), pins)
        self.assertIn(str(m.LARGE[1] / 'first.el'), pins)
        m.complement(self.config)

    def test_actual_three_family_union_and_unchanged_prior_other_metrics(self):
        text = m.union_gate(self.base, self.additions)
        old, new = m.stable.semantic(self.base), m.stable.semantic(text)
        self.assertEqual(old[0], new[0])
        before, after = m.frozen.physical(old), m.frozen.physical(new)
        self.assertTrue(all(after[key] & mask == mask for key, mask in before.items()))
        self.assertEqual(sum(bin(v).count('1') for v in after.values()) -
                         sum(bin(v).count('1') for v in before.values()), 9700)
        self.assertEqual(m.stable.semantic_seal(new), m.UNION_SHA)

    def test_complement_rejects_writable_port_extra_bit_missing_object_and_HOLD(self):
        for mutation in ('port', 'retained', 'node', 'HOLD', 'count'):
            bad = copy.deepcopy(self.config)
            if mutation == 'port':
                bad['instances'][0]['signals'][0]['shape']['portnode'] = '1'
            elif mutation == 'retained':
                bad['instances'][0]['retained_target_signal_bits'].pop(next(iter(bad['instances'][0]['retained_target_signal_bits'])))
            elif mutation == 'node':
                bad['instances'][0]['protected'].pop()
            elif mutation == 'HOLD':
                bad['HOLD_included'] = True
            else:
                bad['protected_direction_count'] -= 2
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.complement(bad)

    def test_native_expansion_missing_direction_duplicate_checksum_rejected(self):
        for bad in (self.native.replace('0to1', '1to0'),
                    self.native.replace('3657545390', '3657545391'),
                    self.native.replace(' [2] ', ' [3] '),
                    self.native + self.native):
            with self.assertRaises(ValueError):
                m.large.parse_el(bad, self.config)

    def test_three_family_count_or_cross_overlap_rejected(self):
        for additions in (self.additions[:2], [self.additions[0], self.additions[1], (self.native, 9438)],
                          [self.additions[0], self.additions[1], (self.additions[1][0], 9440)]):
            with self.assertRaises(ValueError):
                m.union_gate(self.base, additions)

    def test_explicit_population_ancestry_no_fork_or_auto_latest(self):
        reader = m.stable.Reader()
        source = dict(input_ledger=['design'] + ['test'] * 781, expected_selected=['selected'] * 781)
        bits = dict(tests=['case'] * 781)
        wrong = (source, {}, '', bits, [], {})
        with patch.object(m.prior, 'approved', return_value=wrong):
            with self.assertRaises(ValueError):
                m.approved(reader, m.OUT / 'foreign/admission-manifest.json', '0' * 64)
            with self.assertRaises(ValueError):
                m.approved(reader, m.BASE, '0' * 64)
        suffix = copy.deepcopy(wrong)
        suffix[4].append(dict(manifest=str(m.BASE), seal=m.BASE_SHA, population=781))
        with patch.object(m.prior, 'approved', return_value=suffix), \
             patch.object(m, 'qualification', side_effect=[('a', 132, {}), ('b', 128, {}), ('c', 9440, {})]), \
             patch.object(m, 'union_gate', return_value='exact'):
            result = m.approved(reader, m.OUT / 'explicit782/admission-manifest.json', 'f' * 64)
            self.assertEqual(result[2], 'exact')

    def test_context_only_private_rebinding_no_frozen_module_mutation(self):
        original = (m.frozen.SCHEMA, m.frozen.BASE, m.frozen.BASE_SHA, m.frozen.FAMILIES)
        prepare, check, verify, run = m.context(m.BASE, m.BASE_SHA)
        self.assertIs(check.__code__, m.frozen.check.__code__)
        self.assertIs(verify.__code__, m.frozen.verify.__code__)
        self.assertIs(run.__code__, m.frozen.run.__code__)
        self.assertIs(check.__globals__['approved'], m.approved)
        self.assertEqual(check.__globals__['SCHEMA'], m.SCHEMA)
        self.assertEqual(check.__globals__['metadata']()['additional_direction_count'], 9700)
        self.assertEqual(original, (m.frozen.SCHEMA, m.frozen.BASE, m.frozen.BASE_SHA, m.frozen.FAMILIES))
        captured = {}
        def construct(code, namespace):
            self.assertIs(code, m.frozen.prepare.__code__)
            captured.update(namespace)
            return lambda *args: args
        with patch.object(m, 'FunctionType', side_effect=construct):
            prepare(Path('/unused'), 'ara-test.service')
        self.assertEqual(captured['BASE'], m.BASE)
        self.assertEqual(captured['BASE_SHA'], m.BASE_SHA)
        self.assertEqual(captured['__file__'], m.__file__)

    def test_actual781_manifest_authority_and_780_prefix(self):
        reader = m.stable.Reader()
        manifest = reader.read(m.BASE, m.BASE_SHA, True)
        self.assertIs(manifest['coverage_admitted'], True)
        self.assertEqual(manifest['baseline_seal'], m.frozen.BASE_SHA)
        target = m.BASE.parent / 'combined-inputs.txt'
        ledger = reader.read(target, manifest['output_pins'][str(target)]).decode().splitlines()
        previous = (m.frozen.BASE.parent / 'combined-inputs.txt').read_text().splitlines()
        self.assertEqual(len(ledger), 782)
        self.assertEqual(ledger[:-1], previous)
        self.assertEqual(len(set(ledger)), 782)


if __name__ == '__main__':
    unittest.main()
