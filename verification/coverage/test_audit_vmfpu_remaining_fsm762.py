import unittest
import audit_vmfpu_remaining_fsm762 as audit


class AuditTests(unittest.TestCase):
    def test_source_and_queue_induction(self):
        audit.source_controls(audit.SOURCE.read_text())
        for depth in (1, 2, 4, 8, 16):
            self.assertEqual(audit.induction(depth)['counterexamples'], 0)

    def test_extra_entry_and_counter_writer_rejected(self):
        text = audit.SOURCE.read_text()
        for suffix in ('\nmfpu_state_d = SIMD_REDUCTION;',
                       '\nvinsn_queue_d.issue_cnt -= 1;'):
            with self.assertRaises(ValueError):
                audit.source_controls(text + suffix)

    def test_lane_guard_and_accept_guard_rejected(self):
        text = audit.SOURCE.read_text()
        for mutated in (text.replace("if (lane_id_i == '0) begin", "if (lane_id_i != '0) begin"),
                        text.replace("vinsn_queue_d.issue_cnt == '0 && !prevent_commit", '1')):
            with self.assertRaises(ValueError):
                audit.source_controls(mutated)

    def test_reset_protected_not_unreachable(self):
        for lane in range(4):
            for pos in audit.RESET_POSITIONS[lane != 0]:
                point = dict(machine='mfpu_state_q', kind='Transition', raw_position=pos,
                             name='INTRA_LANE_REDUCTION->NO_REDUCTION', source_line='2733')
                self.assertEqual(audit.classify(lane, point),
                                 'REACHABLE_EXTERNAL_RESET_MISSING_PROTECTED')
                point['source_line'] = '740'
                with self.assertRaises(ValueError): audit.classify(lane, point)

    def test_state_lane_identity(self):
        p = dict(machine='mfpu_state_q', kind='State', raw_position=3, name='LN0_REDUCTION_COMMIT')
        audit.classify(0, p)
        with self.assertRaises(ValueError): audit.classify(1, p)

    def test_actual_source_raw_contract(self):
        result = audit.collect()
        self.assertEqual(len(result['points']), 30)
        self.assertEqual(sorted(result['counts'].values()), [4, 6, 20])
        self.assertFalse(result['focused_stimulus']['launch_ready'])


if __name__ == '__main__':
    unittest.main()
