"""Host-only tests of independent coverage and exact assertion classification."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import unittest
from unittest.mock import patch

import run_weight_wide_mapper as m


@lru_cache(None)
def fixture():
    rows = m.expected_coverage()
    lines = ['WIDE_MAPPER_EPOCH epoch=2', 'WIDE_REDUCTION_PASS vectors=1282']
    lines += ['WIDE_PROFILE_PASS ' + ' '.join(f'{k}={v}' for k, v in row.items()) for row in rows]
    keys = ('cases', 'packets', 'decoded', 'payload', 'side', 'lasts')
    total = {key: sum(row[key] for row in rows) for key in keys}
    total.update(abort_cases=36, discarded=1076, accepted=total['decoded'] + 1076, stalls=1, output_stalls=1)
    lines.append('WIDE_MAPPER_COMPONENT_PASS ' + ' '.join(f'{k}={v}' for k, v in total.items()))
    return '\n'.join(lines) + '\n'


class WideMapperCheckerTests(unittest.TestCase):
    def test_v1_log_cannot_be_accepted_as_v2(self):
        with self.assertRaisesRegex(ValueError, 'v2 execution epoch'):
            m.check(fixture().replace('WIDE_MAPPER_EPOCH epoch=2\n', '').replace('WIDE_REDUCTION_PASS vectors=1282\n', ''))
        for bad in (fixture().replace('epoch=2', 'epoch=1'), fixture().replace('vectors=1282', 'vectors=1281')):
            with self.assertRaises(ValueError):
                m.check(bad)

    def test_explicit_parallel_structure_and_valid_only_reset(self):
        source_path = m.DUT if m.DUT.is_file() else Path(__file__).with_name('qbs_weight_wide_mapper.sv')
        source = source_path.read_text()
        functional = source.split('`ifndef SYNTHESIS', 1)[0]
        for name in ('popcount32', 'first_one32', 'encode_onehot32', 'gen_byte_decode',
                     'gen_payload_segment', 'gen_side_index', 'selected_offset_bits'):
            self.assertIn(name, functional)
        self.assertNotIn('target_row', functional)
        self.assertNotIn('packet_d.count[target', functional)
        self.assertNotIn('packet_q <=', functional.split('always_ff @(posedge clk_i or negedge rst_ni)', 1)[1].split(
            'always_ff @(posedge clk_i)', 1)[0])
        self.assertNotIn('rejection', functional.split('for (genvar b = 0; b < 32; b++) begin : gen_byte_decode', 1)[1].split(
            'assign ready_o', 1)[0])
        self.assertIn('halves[0]', functional)
        self.assertIn('select16', functional)

    def test_exact_decoded_payload_side_and_packet_totals(self):
        measured = m.check(fixture())['totals']
        self.assertEqual({k: measured[k] for k in ('cases', 'packets', 'decoded', 'payload', 'side', 'lasts')},
                         dict(cases=4608, packets=40452, decoded=1044480, payload=921600, side=122880, lasts=15360))
        self.assertEqual(measured['accepted'] - measured['decoded'], 1076)

    def test_each_native_region_bijection_and_true_payload_end(self):
        for profile, (size, ls, ln, hs, hn, sides) in m.REGIONS.items():
            destinations = [m.locate(profile, b)[:2] for b in range(size)]
            self.assertEqual(len(set(destinations)), size)
            self.assertEqual(sum(m.locate(profile, b)[2] for b in range(size)), 1 + int(hn != 0))
            self.assertTrue(m.locate(profile, ls + ln - 1)[2])
            self.assertTrue(all(0 <= m.locate(profile, b)[1] < (20 if m.locate(profile, b)[0] == 2 else 256)
                                for b in range(size)))
        self.assertTrue(m.locate(2, 127)[2])
        self.assertTrue(m.locate(2, 191)[2])
        self.assertTrue(m.locate(7, 79)[2])
        self.assertEqual(m.locate(7, 80)[:2], (2, 16))

    def test_missing_duplicate_corrupt_coverage_and_decoded_bytes_rejected(self):
        text = fixture()
        broken = (text.split('\n', 1)[1], text + text, text.replace('decoded=1044480', 'decoded=1044479'),
                  text.replace('cases=512', 'cases=511', 1), text.replace('profile=9', 'profile=8'),
                  text.replace('stalls=1', 'stalls=0'), text.replace('packets=40452', 'packets=40451'),
                  text + 'Fatal: simulated returncode zero\n')
        for value in broken:
            with self.assertRaises(ValueError):
                m.check(value)

    def test_nonzero_head_full_tail_and_multibank_coverage(self):
        for row in m.expected_coverage():
            self.assertEqual(row['cases'], 512)
            for key in ('heads', 'fulls', 'tails', 'cross_rows', 'cross_planes'):
                self.assertGreater(row[key], 0)

    def test_exact_expected_fatal_can_have_returncode_zero_but_never_normal_pass(self):
        for name, reason in m.REJECTIONS.items():
            text = f'WIDE_NEGATIVE_ARMED name={name}\nFatal: QBS_WIDE_REJECT_{reason}\nFile: qbs_weight_wide_mapper.sv\n'
            for code in (0, 1):
                row = m.check_rejection(text, name, code)
                self.assertEqual(row['classification'], 'expected_contract_rejection_not_normal_functional_PASS')
            with self.assertRaises(ValueError):
                m.check(text)
            for broken in (text.replace('Fatal:', ''), text.replace(reason, 'WRONG'),
                           text + fixture(), text + 'WIDE_NEGATIVE_NOT_REJECTED\n',
                           text.replace('qbs_weight_wide_mapper.sv', 'wrong_file.sv'), text + text):
                with self.assertRaises(ValueError):
                    m.check_rejection(broken, name, 0)

    def test_duplicate_fields_and_unknown_record_rejected(self):
        with self.assertRaises(ValueError):
            m.fields('TAG a=1 a=2', 'TAG')
        with self.assertRaises(ValueError):
            m.check(fixture() + 'WIDE_FAKE_PASS\n')

    def test_frozen_pin_cannot_be_replaced(self):
        pins, path = m.Pins(), Path(__file__).resolve()
        with patch.object(m, 'digest', side_effect=['a', 'b', 'b']):
            pins.pin(path)
            with self.assertRaises(ValueError):
                pins.pin(path)
            self.assertEqual(pins.values[str(path)], 'a')
            with self.assertRaises(ValueError):
                pins.verify()

    def test_wrong_or_existing_output_refused_without_writes(self):
        with self.assertRaises(ValueError):
            m.run(Path('/tmp/not-allowed'))
        with patch.object(m, 'inventories', return_value=[]), \
                patch.object(Path, 'mkdir', side_effect=FileExistsError), patch.object(m, 'write_new') as write:
            with self.assertRaises(FileExistsError):
                m.run(m.OUT)
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
