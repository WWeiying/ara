import unittest
from inventory import inventory


class InventoryTests(unittest.TestCase):
    def case(self, sha='a'*64):
        return dict(name='case', sha256=sha, pass_marker='PASS')

    def report(self, status='passed', sha='a'*64):
        return dict(inputs=dict(cases=[self.case(sha)]), rtl_modified=False, board_reset=False,
                    results=[dict(name='case', status=status, exit_code=0 if status=='passed' else 1,
                                  output='PASS cases=4\n' if status=='passed' else 'FAIL cases=4\n')])

    def test_snapshots_and_shared_releases_do_not_duplicate_cases(self):
        manifests = [('a', dict(cases=[self.case()])), ('b', dict(cases=[self.case()]))]
        result = inventory(manifests, [('first', self.report()), ('later', self.report())])
        self.assertEqual(result['planned'], 1)
        self.assertEqual(result['counts'], {'passed': 1})
        self.assertEqual(result['cases'][0]['evidence']['passed'], ['first', 'later'])

    def test_running_snapshot_is_superseded_by_completed_same_elf(self):
        result = inventory([('a', dict(cases=[self.case()]))],
                           [('live', self.report('running')), ('done', self.report())])
        self.assertEqual(result['counts'], {'passed': 1})

    def test_pass_does_not_erase_failure_or_stall(self):
        for status in ('failed', 'stalled', 'incomplete'):
            result = inventory([('a', dict(cases=[self.case()]))],
                               [('old', self.report(status)), ('new', self.report())])
            self.assertEqual(result['counts'], {'mixed_outcomes': 1})
            self.assertFalse(result['all_selected_elves_finished'])
            self.assertEqual(result['elves_with_completed_numerical_result'],1)
            self.assertEqual(result['historical_incomplete_with_completed_result'],int(status=='incomplete'))

    def test_different_binary_same_name_is_not_board_coverage(self):
        result = inventory([('new', dict(cases=[self.case('b'*64)]))], [('old', self.report())])
        self.assertEqual(result['counts'], {'not_attempted': 1})
        self.assertEqual(result['elves_with_completed_numerical_result'],0)
        self.assertEqual(len(result['outside_selected_releases']), 1)

    def test_false_marker_and_changed_board_rejected(self):
        for mode in ('echo', 'duplicate', 'reset', 'rtl'):
            report = self.report()
            if mode == 'echo': report['results'][0]['output'] = 'echo PASS cases=4\n'
            if mode == 'duplicate': report['results'][0]['output'] *= 2
            if mode == 'reset': report['board_reset'] = True
            if mode == 'rtl': report['rtl_modified'] = True
            with self.assertRaises(ValueError):
                inventory([('a', dict(cases=[self.case()]))], [('bad', report)])

    def test_signal_exit_without_numeric_marker_is_not_numeric_coverage(self):
        report=self.report('failed')
        report['results'][0].update(exit_code=132,output='Illegal instruction\n')
        result=inventory([('a',dict(cases=[self.case()]))],[('signal',report)])
        self.assertEqual(result['counts'],{'failed':1})
        self.assertEqual(result['elves_with_completed_numerical_result'],0)


if __name__ == '__main__':
    unittest.main()
