import unittest

import check_supply_sdk as c
from test_supply_decode import stream
from test_full_projection import fixture


def full_stream(width):
    text, golden = fixture(1); lines = []
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            row = c.decode.fields(line, '[QBS_PERF]')
            profile = 1 if row['seq'] <= 96 else 2
            for key in (*c.decode.COUNTERS, *c.decode.WAIT, *c.decode.CONTEXT_COUNTERS): row.setdefault(key, 0)
            weight_beats = ((36 if width == 128 else 18) if profile == 1 else (53 if width == 128 else 27))
            row.update(payload_bytes=16 + row['weight_bytes'] + row['activation_bytes'], read_ranges=73, ar=73,
                       r_beats=1 + 64 * weight_beats + 584)
            for phase in c.decode.PHASES: row['phase_' + phase + '_cycles'] = 0
            row['phase_setup_cycles'] = row['busy_cycles']
            c.decode.read_contract(row, width, 8, profile, 4)
            line = '[QBS_PERF] ' + ' '.join(k + '=' + str(v) for k,v in row.items())
        lines.append(line)
    return '\n'.join(lines), golden


class SupplySDKTests(unittest.TestCase):
    def test_old_full_functional_checks_preserved(self):
        for width in (128, 256):
            text, golden = full_stream(width)
            value = c.check(text, 'prefill', width, golden)
            self.assertEqual({k: v for k,v in value.items() if k != 'counters'}, c.prefill.check(text, 1, golden))
            self.assertEqual(value['dot_issue_count'], 524288)

    def test_full_rejects_missing_ranges_bad_reader_and_changed_math(self):
        text, golden = full_stream(256)
        for old, new in (('read_ranges=73', 'read_ranges=72'), ('activation_bytes=9344', 'activation_bytes=0'),
                         ('r_beats=1737', 'r_beats=1736'), ('context_reuse_count=0', 'context_reuse_count=1'),
                         ('dot_active_cycles=4096', 'dot_active_cycles=8192'), ('fcsr=9', 'fcsr=8'),
                         ('phase_setup_cycles=6000', 'phase_setup_cycles=5999')):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(ValueError):
                c.check(text.replace(old, new, 1), 'prefill', 256, golden)

    def test_pair_reports_outcomes_without_requiring_speedup(self):
        for kind in ('decode', 'prefill'):
            if kind == 'decode':
                text, *oracle = stream(128)
            else: text, oracle = full_stream(128)
            a = c.check(text, kind, 128, oracle)
            pair = c.paired(a, a, kind)
            self.assertEqual(pair['speedups']['region'], 1)
            self.assertFalse(pair['region_cycles_reduced_at_least_10_percent'])
            self.assertFalse(pair['region_regression_above_2_percent'])
            b = dict(a, useful_pairs=a['useful_pairs'] - 1)
            with self.assertRaises(ValueError): c.paired(a, b, kind)


if __name__ == '__main__': unittest.main()
