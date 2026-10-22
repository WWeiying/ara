"""Actual complete native EL positives and typed/source/direction schema negatives."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import fma_expanded_native_04 as native
import fma_expanded_session_mock_04 as mock


class RealELTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.evidence = native.fixture()
        cls.text = (native.OLD / 'first.el').read_text()
        cls.scalar = 'Toggle 0to1 tentative_sign "logic tentative_sign"'
        cls.reverse = 'Toggle 1to0 tentative_sign "logic tentative_sign"'
        cls.whole = 'Toggle tentative_sign "logic tentative_sign"'
        cls.array = 'Toggle mid_pipe_tent_exp_q "logic [0:2][12:0]mid_pipe_tent_exp_q"'

    def test_actual_complete_612_native_schema(self):
        records = native.parse_el(self.text, self.c)
        self.assertEqual(len(records), 612)
        self.assertEqual(len([l for l in self.text.splitlines() if l.startswith('Toggle ')]), 684)
        self.assertEqual(sum(json.loads(r[-1])['source_signed'] for r in records), 192)
        self.assertEqual(sum(json.loads(r[-1])['struct_declaration'] is not None for r in records), 108)
        self.assertEqual(native.life.digest(native.OLD / 'first.el'), native.FIRST_SHA)

    def test_scalar_whole_equals_complete_pair_and_pair_order(self):
        whole = self.text.replace(self.scalar + '\n' + self.reverse, self.whole, 1)
        reverse_order = self.text.replace(self.scalar + '\n' + self.reverse, self.reverse + '\n' + self.scalar, 1)
        records = native.parse_el(self.text, self.c)
        self.assertEqual(records, native.parse_el(whole, self.c))
        self.assertEqual(records, native.parse_el(reverse_order, self.c))

    def test_nonscalar_whole_equals_complete_pair(self):
        pair = self.array.replace('Toggle ', 'Toggle 0to1 ', 1) + '\n' + self.array.replace('Toggle ', 'Toggle 1to0 ', 1)
        self.assertEqual(native.parse_el(self.text, self.c), native.parse_el(self.text.replace(self.array, pair, 1), self.c))

    def test_full_prefix_suffix_dimensions_preserve_identity(self):
        suffix = 'Toggle mid_pipe_tent_exp_q "logic mid_pipe_tent_exp_q[0:2][12:0]"'
        self.assertEqual(native.parse_el(self.text, self.c), native.parse_el(self.text.replace(self.array, suffix, 1), self.c))

    def test_real_EL_direction_negatives(self):
        negatives = {
            'missing_forward': self.text.replace(self.scalar + '\n', '', 1),
            'missing_reverse': self.text.replace(self.reverse + '\n', '', 1),
            'duplicate_forward': self.text.replace(self.reverse, self.scalar, 1),
            'duplicate_reverse': self.text.replace(self.scalar, self.reverse, 1),
            'mixed': self.text.replace(self.scalar, self.whole + '\n' + self.scalar, 1),
            'duplicate_whole': self.text.replace(self.array, self.array + '\n' + self.array, 1),
            'unknown_direction': self.text.replace(self.scalar, self.scalar.replace('0to1', 'rise'), 1),
            'wrong_pair_type': self.text.replace(self.reverse, self.reverse.replace('"logic ', '"reg '), 1),
            'wrong_pair_name': self.text.replace(self.reverse, self.reverse.replace('tentative_sign"', 'final_sign"'), 1),
        }
        for label, text in negatives.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                native.parse_el(text, self.c)

    def test_real_EL_identity_negatives(self):
        negatives = {
            'checksum': self.text.replace('2431620414', '2431620415', 1),
            'toggle_checksum': self.text.replace('1358950482', '1358950483', 1),
            'child': self.text.replace('.i_fma\n', '.i_fma.i_lzc\n', 1),
            'scalar_fpu': self.text.replace('i_vmfpu', 'i_scalar_fpu', 1),
            'QBS': self.text.replace('i_vmfpu', 'i_qbs', 1),
            'FP16': self.text.replace('gen_parallel_slices[1]', 'gen_parallel_slices[2]', 1),
            'wrong_metric': self.text.replace('Toggle ', 'Line ', 1),
            'wrong_type': self.text.replace('"logic ', '"reg ', 1),
            'unknown_qualifier': self.text.replace('"logic ', '"logic unsigned ', 1),
            'unobserved_native_signed': self.text.replace(self.array, self.array.replace('"logic ', '"logic signed '), 1),
            'scalar_fake_bounds': self.text.replace('"logic tentative_sign"', '"logic tentative_sign[0:0]"', 1),
            'partial_array': self.text.replace(self.array, self.array.replace('[0:2]', '[0:1]'), 1),
            'reverse_dimension': self.text.replace(self.array, self.array.replace('[0:2]', '[2:0]'), 1),
            'drop_dimension': self.text.replace(self.array, self.array.replace('[0:2]', ''), 1),
            'reorder_dimensions': self.text.replace(self.array, self.array.replace('[0:2][12:0]', '[12:0][0:2]'), 1),
            'split_prefix_suffix': self.text.replace(self.array, 'Toggle mid_pipe_tent_exp_q "logic [0:2]mid_pipe_tent_exp_q[12:0]"', 1),
            'struct_field': self.text.replace('"logic operand_a.sign"', '"logic operand_a.mantissa"', 1),
            'port': self.text + 'Toggle busy_o "logic busy_o"\n',
            'control': self.text + 'Toggle effective_subtraction "logic effective_subtraction"\n',
            'rounding': self.text + 'Toggle pre_round_abs "logic pre_round_abs[63:0]"\n',
            'status': self.text + 'Toggle status_o.NV "logic status_o.NV"\n',
            'mask': self.text + 'Toggle mid_pipe_mask_q "logic mid_pipe_mask_q[0:2]"\n',
            'missing_object': self.text.replace(self.array + '\n', '', 1),
            'trailing_checksum': self.text + 'CHECKSUM: "2431620414 1358950482"\n',
        }
        for label, text in negatives.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                native.parse_el(text, self.c)

    def test_configuration_source_schema_negatives(self):
        for field, value in [('type', '2'), ('portnode', '1'), ('line_num', '404'),
                             ('dimensions', [[1, 2]]), ('shape_kind', 'node')]:
            c = copy.deepcopy(self.c)
            c['instances'][0]['targets'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                native.parse_el(self.text, c)
        c = copy.deepcopy(self.c)
        c['source_type_bindings'] = [dict(scope=k[0], name=k[1], **v) for k, v in native.source_bindings(c).items()]
        c['source_type_bindings'][0]['source_signed'] = True
        with self.assertRaises(ValueError):
            native.parse_el(self.text, c)

    def test_actual_disk_entry_real_EL_five_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            native.write_selection(out)
            evidence = mock.qualify_disk_entry(out / 'selection.tcl')
        self.assertEqual([s['stage'] for s in evidence['stages']], list(native.frozen.STAGES))
        self.assertTrue(all(s['objects'] == 612 and s['all_nontarget_objects'] == 2832 for s in evidence['stages']))
        self.assertFalse(evidence['native_qualification'])


if __name__ == '__main__':
    unittest.main()
