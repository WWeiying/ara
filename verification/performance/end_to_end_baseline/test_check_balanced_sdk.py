import copy
import unittest

import check_balanced_sdk as c
from test_supply_sdk import full_stream
from test_ffn_native import fixture as ffn_fixture


def inputs(kind, balanced):
    if kind == 'prefill':
        text, expected = full_stream(256)
    else:
        text, *expected = ffn_fixture(1)
        lines = []
        for line in text.splitlines():
            if line.startswith('[QBS_PERF] '):
                row = c.supply.decode.fields(line, '[QBS_PERF]')
                blocks = 8 if row['seq'] <= 8 else 24
                weight_beats = 18 if row['seq'] <= 8 else 27
                for key in c.SERVICE:
                    row.setdefault(key, 0)
                row.update(payload_bytes=16 + row['weight_bytes'] + row['activation_bytes'],
                           read_ranges=1 + 9 * blocks, ar=1 + 9 * blocks,
                           r_beats=1 + 8 * blocks * weight_beats + blocks * 73)
                line = '[QBS_PERF] ' + ' '.join(k + '=' + str(v) for k, v in row.items())
            lines.append(line)
        text = '\n'.join(lines)
    if balanced:
        lines = []
        for line in text.splitlines():
            if line.startswith('[QBS_PERF] '):
                row = c.supply.decode.fields(line, '[QBS_PERF]')
                row['dot_active_cycles'] //= 2
                line = '[QBS_PERF] ' + ' '.join(k + '=' + str(v) for k, v in row.items())
            lines.append(line)
        text = '\n'.join(lines)
    return text + '\nCore Test *** SUCCESS *** (tohost = 0)\n', expected


class BalancedSdk(unittest.TestCase):
    def test_specialization_has_only_structural_count_edit_and_no_global_mutation(self):
        old_full = c.full.check
        old_supply = c.supply.prefill
        for parent in c.REPLACEMENTS:
            fn, record = c.specialize(parent)
            self.assertTrue(record['source_reversible'])
            self.assertFalse(record['numerical_checks_changed'])
            self.assertIsNot(fn, parent.check)
        for kind in ('prefill', 'ffn'):
            text, expected = inputs(kind, 0)
            a = c.check(text, kind, 0, expected)
            text, expected = inputs(kind, 1)
            b = c.check(text, kind, 1, expected)
            result = c.pair(a, b)
            self.assertEqual(result['ratios']['region'], 1)
            self.assertEqual(a['measured']['dot_issue_count'], 2 * b['measured']['dot_issue_count'])
        self.assertIs(c.full.check, old_full)
        self.assertIs(c.supply.prefill, old_supply)

    def test_candidate_rejects_old_count_altered_outputs_state_and_service(self):
        for kind in ('prefill', 'ffn'):
            text, expected = inputs(kind, 1)
            for old, new in (('dot_active_cycles=2048', 'dot_active_cycles=4096'),
                             ('errors=0', 'errors=1'), ('fcsr=9', 'fcsr=8'),
                             ('r_beats=1737', 'r_beats=1736'),
                             ('activation_bytes=9344', 'activation_bytes=9343'),
                             ('tohost = 0', 'tohost = 1')):
                self.assertIn(old, text)
                with self.subTest(kind=kind, old=old), self.assertRaises(ValueError):
                    c.check(text.replace(old, new, 1), kind, 1, expected)
            original, _ = inputs(kind, 0)
            with self.assertRaises(ValueError):
                c.check(original, kind, 1, expected)
            with self.assertRaises(ValueError):
                c.check(text, kind, 0, expected)

    def test_pair_rejects_changed_work_and_does_not_assume_speedup(self):
        for kind in ('prefill', 'ffn'):
            text, expected = inputs(kind, 0)
            a = c.check(text, kind, 0, expected)
            text, expected = inputs(kind, 1)
            b = c.check(text, kind, 1, expected)
            bad = copy.deepcopy(b)
            bad['service']['weight_bytes'] -= 1
            with self.assertRaises(ValueError):
                c.pair(a, bad)
            key = 'trials' if kind == 'prefill' else 'total'
            row = b['measured'][key][0] if kind == 'prefill' else b['measured'][key]
            row['region'] += 100
            self.assertLess(c.pair(a, b)['ratios']['region'], 1)

    def test_explicit_geometry_required(self):
        for kind, balanced in (('decode', 1), ('prefill', True), ('ffn', 2)):
            with self.assertRaises(ValueError):
                c.checker(kind, balanced)


if __name__ == '__main__':
    unittest.main()
