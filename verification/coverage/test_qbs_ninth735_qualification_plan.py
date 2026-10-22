import copy
import unittest

import prepare_qbs_ninth735_qualification_plan as p


class Ninth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.actual=p.evidence()

    def test_actual_exact735_and_zero1792(self):
        self.assertEqual(self.actual['exact_population'],735)
        self.assertTrue(self.actual['source735_zero_check']['still_zero'])
        self.assertFalse(self.actual['launch_ready']);self.assertFalse(self.actual['final_application'])

    def test_calls_are_sixstages_and_not_complete_GUI_count(self):
        c=self.actual['call_budget']
        self.assertEqual(c['excluded_status_query_calls']['total_six_stages'],163500)
        self.assertEqual(c['per_stage_GUI_core_calls']['new9_lower'],29572)
        self.assertEqual(c['per_stage_GUI_core_calls']['new9_upper'],34500)
        self.assertEqual(c['budget_seconds'],14400)
        self.assertTrue(c['not_complete_total_GUI_count']);self.assertFalse(c['automatic_retry'])

    def test_constant_interpreter_rejects_source_exec_file_GUI(self):
        for text in ('source /tmp/x','exec true','open /tmp/x w','gui_exclusion -reset'):
            with self.subTest(text=text),self.assertRaises(ValueError):p.constant_selection(text,'qbs')

    def test_wrong_counts_rejected_not_zero_or_skip(self):
        six=copy.deepcopy(self.actual['six_selection_inventory']);six['qbs']['audited_points']-=1
        with self.assertRaises(ValueError):p.calls(six,self.actual['lzc_selection_inventory'])
        lzc=copy.deepcopy(self.actual['lzc_selection_inventory']);lzc['condition_rows']-=1
        with self.assertRaises(ValueError):p.calls(self.actual['six_selection_inventory'],lzc)
        with self.assertRaises(ValueError):p.lzc_counts('set seven_rows {}\n')


if __name__=='__main__':unittest.main()
