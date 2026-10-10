import copy
import unittest
import summarize_qbs_hit_batch780 as s


class PartitionTests(unittest.TestCase):
    def setUp(self):
        self.item = dict(scope='x.bank0.i_payload_buffer', checksum='3657545390',
            signal='gen_side_row[0].gen_activation_byte[1].hit', bit=18,
            raw_coordinates=[100, 101], classification='SOURCE_MAPPING_ZERO_NATIVE_REQUIRED', mapping_witness=None)

    def test_original_side_writer_identity(self):
        r = s.compact([self.item], set())
        self.assertEqual(r['target_groups'][0]['original_writer_slots']['18'], [1, 2])
        self.assertEqual(r['counts'], {'NEW_ZERO_NATIVE_REQUIRED': 2})

    def test_qualified128_separate_not_applied(self):
        i = self.item
        r = s.compact([i], {(i['scope'], i['signal'], i['bit'])})
        self.assertEqual(r['counts'], {'QUALIFIED128_NOT_APPLIED': 2})

    def test_HOLD_never_promoted(self):
        i = dict(self.item, classification='MAPPING_WITNESS_ARBITRATION_HOLD', raw_coordinates=[101])
        r = s.compact([i], set())
        self.assertEqual(len(r['target_groups']), 0)
        self.assertEqual(r['counts'], {'HOLD_MAPPING_NOT_RUNTIME_PROOF': 1})

    def test_duplicate_or_observed_zero_rejected(self):
        with self.assertRaises(ValueError): s.compact([self.item, self.item], set())
        bad = copy.deepcopy(self.item)
        bad['raw_coordinates'].pop()
        with self.assertRaises(ValueError): s.compact([bad], set())


if __name__ == '__main__': unittest.main()
