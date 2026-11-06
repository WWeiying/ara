"""The width successor must retain all old functional gates, not just cycles."""
from pathlib import Path
import unittest

import check_supply_decode as c
import check_decode_native as legacy
from test_decode_native import fixture


def stream(bus_bits):
    text, *oracle = fixture()
    rows, totals = [], [0]*7
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            row = c.fields(line, '[QBS_PERF]')
            part = (row['seq']-1)//4
            blocks = c.K[part]//256
            row['read_ranges'] = 1+8*blocks+(0 if row['activation_access'] in (2,3) else blocks)
            row['ar'] = row['read_ranges']
            weight_beats = ((36 if bus_bits == 128 else 18) if c.PROFILE[part] == 1
                            else (53 if bus_bits == 128 else 27))
            row['r_beats'] = 1+8*blocks*weight_beats+(0 if row['activation_access'] in (2,3) else blocks*19)
            row['busy_cycles'] = max(row['busy_cycles'], row['r_beats'])
            row['phase_setup_cycles'] = row['busy_cycles']
            totals[part] += row['busy_cycles']
            rows.append(('[QBS_PERF]', row))
        elif line.startswith(('DECODE_NATIVE_PART ', 'DECODE_NATIVE_RESULT ')):
            tag = line.split()[0]; rows.append((tag, c.fields(line, tag)))
        else: rows.append((None, line))
    result = []
    for tag, row in rows:
        if tag == 'DECODE_NATIVE_PART': row['execution'] = totals[row['part']]+200
        if tag == 'DECODE_NATIVE_RESULT':
            row['execution'] = sum(totals)+1400; row['region'] = row['execution']+500
        result.append(tag+' '+' '.join(k+'='+str(v) for k,v in row.items()) if tag else row)
    return '\n'.join(result), *oracle


class SupplyDecodeTests(unittest.TestCase):
    def test_original_results_retained_at_128(self):
        args = stream(128)
        self.assertEqual(c.check(*args, 128), legacy.check(*args))

    def test_narrow_activations_not_counted_as_32byte_transfers(self):
        args = stream(256)
        measured = c.check(*args, 256)
        self.assertEqual(measured['commands'], 28)
        self.assertEqual(measured['useful_pairs'], 2359296)
        with self.assertRaises(ValueError): legacy.check(*args)
        line = next(s for s in args[0].splitlines() if s.startswith('[QBS_PERF] '))
        row = c.fields(line, '[QBS_PERF]')
        correct = row['r_beats']; wrong = (row['payload_bytes']+31)//32
        self.assertGreater(correct, wrong)
        with self.assertRaises(ValueError):
            c.check(args[0].replace(f'r_beats={correct} ', f'r_beats={wrong} ', 1), *args[1:], 256)

    def test_read_range_and_existing_functional_mutations_fail(self):
        args = stream(256)
        for old,new in (('read_ranges=73', 'read_ranges=72'), (' ar=73 ', ' ar=72 '),
                        ('fcsr=9', 'fcsr=8'), ('context_read_bytes=2336', 'context_read_bytes=0'),
                        ('dot_active_cycles=2048', 'dot_active_cycles=2047'),
                        ('outputs=896', 'outputs=895'), ('vstart=0', 'vstart=1'), ('errors=0', 'errors=1')):
            self.assertIn(old, args[0])
            with self.subTest(old=old), self.assertRaises(ValueError):
                c.check(args[0].replace(old,new,1), *args[1:], 256)

    def test_missing_or_duplicate_command_and_bad_oracle_fail(self):
        args = stream(256); line = next(s for s in args[0].splitlines() if s.startswith('[QBS_PERF] '))
        for text in (args[0]+'\n'+line, args[0].replace(line, '', 1)):
            with self.assertRaises(ValueError): c.check(text, *args[1:], 256)
        args[1][0] = bytes(512)
        with self.assertRaises(ValueError): c.check(*args, 256)

    def test_narrow_weight_service_rejected_on_wide_processor(self):
        args = stream(128)
        with self.assertRaisesRegex(ValueError, 'Physical transfer'):
            c.check(*args, 256)


if __name__ == '__main__': unittest.main()
