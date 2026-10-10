import unittest

from report_scope_ancestors import report_ancestors


class ReportAncestorTests(unittest.TestCase):
    def test_merged_generate_name_is_one_node(self):
        rows = [dict(Name='ara_tb', Depth='0'),
                dict(Name='gen_lanes[0].i_lane', Depth='1'),
                dict(Name='i_queue', Depth='2')]
        self.assertEqual(report_ancestors(rows, {'ara_tb.gen_lanes[0].i_lane.i_queue'}),
                         ['ara_tb', 'ara_tb.gen_lanes[0].i_lane',
                          'ara_tb.gen_lanes[0].i_lane.i_queue'])

    def test_missing_scope_rejected(self):
        with self.assertRaises(ValueError):
            report_ancestors([dict(Name='ara_tb', Depth='0')], {'ara_tb.missing'})

    def test_depth_jump_and_duplicate_rejected(self):
        for rows in ([dict(Name='ara_tb', Depth='0'), dict(Name='child', Depth='2')],
                     [dict(Name='ara_tb', Depth='0'), dict(Name='ara_tb', Depth='0')]):
            with self.assertRaises(ValueError):
                report_ancestors(rows, {'ara_tb'})


if __name__ == '__main__':
    unittest.main()
