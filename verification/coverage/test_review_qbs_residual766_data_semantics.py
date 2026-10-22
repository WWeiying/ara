import copy
import unittest

import review_qbs_residual766_data_semantics as m


class DataSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = m.load_verified()
        cls.source = (m.ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv').read_text()
        cls.field = next(p for p in cls.data['all_typed_fields']
                         if p['module'] == 'qbs_payload_buffer'
                         and p['name'].endswith('.older') and p['missing'])

    def test_actual_all_pins_and_all_selection_bytes(self):
        result = m.review(self.data)
        self.assertEqual(result['typed_sram_data_missing'], 0)
        self.assertEqual(result['selection_data_missing'], 0)
        self.assertGreater(result['selection_valid_missing'], 0)
        self.assertIsNone(result['predicted_gain'])
        self.assertFalse(result['coverage_admitted'])

    def test_missing_valid_is_not_data(self):
        result = m.split_selection(self.field, self.source)
        self.assertEqual(result['data_7_0_missing'], 0)
        self.assertEqual(result['valid_8_missing'], 2)

    def test_real_data_missing_is_not_skipped(self):
        p = copy.deepcopy(self.field)
        p['missing_coordinates'].append(p['raw_offset'])
        p['missing'] += 1
        self.assertEqual(m.split_selection(p, self.source)['data_7_0_missing'], 1)

    def test_shape_port_and_source_mismatch_rejected(self):
        for key, value in [('left', '9'), ('right', '1'), ('portnode', '3'), ('excluded', '1')]:
            p = copy.deepcopy(self.field); p['attributes'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.split_selection(p, self.source)
        p = copy.deepcopy(self.field); p['source_binding']['line'] += 1
        with self.assertRaises(ValueError): m.split_selection(p, self.source)

    def test_bad_coordinates_and_valid_fanout_rejected(self):
        p = copy.deepcopy(self.field); p['missing_coordinates'][0] = p['raw_offset'] + 18
        with self.assertRaises(ValueError): m.split_selection(p, self.source)
        changed = self.source.replace('byte_valid = source_valid && selected[8]',
                                      'byte_valid = source_valid && selected[7]')
        with self.assertRaises(ValueError): m.split_selection(self.field, changed)

    def test_array_capacity_not_invented(self):
        data = copy.deepcopy(self.data)
        data['all_arrays_without_binary_coordinate'][0]['missing'] = 0
        with self.assertRaises(ValueError): m.review(data)


if __name__ == '__main__':
    unittest.main()
