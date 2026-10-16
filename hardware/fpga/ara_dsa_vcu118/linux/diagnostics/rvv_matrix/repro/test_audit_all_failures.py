import unittest
from audit_all_failures import identity, issue_routes


class AuditTests(unittest.TestCase):
    def test_status_boundaries(self):
        self.assertEqual(issue_routes('rvv_permute_restart_e8_m8', 'not_attempted'),
                         ['unexecuted_not_a_failure'])
        self.assertEqual(issue_routes('rvv_memory_restart_e8_m8', 'mixed_outcomes'),
                         ['observation_gap_not_established_rtl_failure'])

    def test_memory_distinctions(self):
        self.assertEqual(issue_routes('rvv_fault_replay_strided_zero_stride_e64_m2', 'stalled'), ['RVV-16'])
        self.assertNotEqual(issue_routes('rvv_fault_replay_strided_zero_stride_e64_m2', 'failed'), ['RVV-16'])
        self.assertEqual(issue_routes('rvv_fault_replay_segment_nf7_indexed_e32_mf2', 'failed'), ['RVV-15'])

    def test_setup_is_not_segment_target(self):
        self.assertEqual(issue_routes('rvv_segments_misaligned_e16_m1', 'failed'), ['CAP-01'])
        self.assertEqual(issue_routes('rvv_segment_alignment_e16_m1', 'stalled'), ['RVV-18'])

    def test_identity_and_unknown(self):
        row = dict(scope='original', name='x', sha256='a')
        self.assertNotEqual(identity(row), identity(dict(row, sha256='b')))
        self.assertEqual(issue_routes('new_unrecognized_test', 'failed'), ['UNMAPPED'])


if __name__ == '__main__':
    unittest.main()
