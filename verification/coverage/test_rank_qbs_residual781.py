import unittest
import rank_qbs_residual781 as r


class RankingTests(unittest.TestCase):
    def test_selected_data_valid_separate(self):
        field = dict(name='gen_byte_merge[0].selected', module='qbs_payload_buffer')
        self.assertEqual(r.category(field, 7), 'SELECTED_DATA')
        self.assertEqual(r.category(field, 8), 'SELECTED_VALID')

    def test_side_offset_not_hit(self):
        self.assertEqual(r.category(dict(name='activation_side_offset', module='qbs_payload_buffer')), 'SIDE_OFFSET')
        self.assertEqual(r.category(dict(name='gen_side_row[0].gen_activation_byte[1].hit', module='qbs_payload_buffer')), 'HIT_SIDE')

    def test_fp32_mask_ascending_not_numeric_lsb(self):
        params = dict(Width=32, NUM_FORMATS=6, FpFmtMask=32, FmtUnitTypes=1365)
        active = dict(module='fpnew_opgroup_block', name='fmt_outputs[0].result')
        self.assertFalse(r.disabled_result(active, params))
        self.assertTrue(r.disabled_result(dict(active, name='fmt_outputs[5].result'), params))
        self.assertTrue(r.disabled_result(active, dict(params, FmtUnitTypes=0)))

    def test_active_flags_and_tag_not_candidate(self):
        params = dict(Width=32, NUM_FORMATS=6, FpFmtMask=32, FmtUnitTypes=0)
        for name in ('result_o', 'fmt_outputs[1].status', 'fmt_outputs[1].tag', 'fflags_o'):
            self.assertFalse(r.disabled_result(dict(module='fpnew_opgroup_block', name=name), params))

    def test_changed_compiled_config_rejected(self):
        f = dict(module='fpnew_opgroup_block', name='fmt_outputs[1].result')
        with self.assertRaises(ValueError): r.disabled_result(f, dict(Width=64, NUM_FORMATS=6, FpFmtMask=32, FmtUnitTypes=1365))


if __name__ == '__main__': unittest.main()
