"""Offline gates, including the original failing RTL trace (no EDA)."""
from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

import audit_mask_restart_repair as repair
import test_mask_compare_restart_known786_run_collect as old_tests


class RepairAuditGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = repair.frozen
        cls.pre, cls.reference_pins = repair.reference_contract()
        cls.reference = cls.c.reference_prefix(cls.pre)
        cls.failed = cls.c.life.OUT / (
            'mask-compare-restart-known-old-image786-agent-20261008-01')
        cls.original_pins = {
            str(cls.failed / name): cls.c.life.digest(cls.failed / name)
            for name in ('commit_trace.csv', 'vector_trace.csv', 'console.log',
                         'run.vcs.log', 'trace_hart_0.log')}

    def tearDown(self):
        self.c.life.check(self.original_pins)

    def test_original_failed_run_is_rejected(self):
        with self.assertRaisesRegex(Exception, 'Simulator/UVM failure'):
            repair.audit(self.failed)

    def test_original_scalar_error_not_hidden_by_success_log(self):
        # Deliberately bypass only the log gate; the real original scalar trace
        # must still fail against the unchanged independent Spike reference.
        with patch.object(self.c.mature, 'logs', return_value=None):
            with self.assertRaisesRegex(Exception, 'Complete scalar comparison differs'):
                repair.audit(self.failed)

    def test_original_native_prestart_error_independently_rejected(self):
        with self.assertRaisesRegex(Exception, 'Prestart bit changed'):
            repair.native(self.failed, self.reference, self.pre['symbols'])

    def test_original_software_signature_independently_rejected(self):
        rows = self.c.common.read_csv(
            (self.failed / 'commit_trace.csv').read_bytes(), self.c.common.COMMIT_FIELDS)
        with self.assertRaises(Exception):
            self.c.footprint(rows, self.pre['symbols'])

    def fixture(self):
        fixture = old_tests.KnownOldGates()
        fixture.pre, fixture.reference = self.pre, self.reference
        activities, mapping, rows = fixture.fixture()
        for seq, activity in activities.items():
            if self.reference[mapping[seq]].pc in (self.pre['symbols']['mc_clear24'],
                                                   self.pre['symbols']['mc_xor']):
                activity.writes = [replace(w, source=0) for w in activity.writes]
        return activities, mapping, rows

    def test_positive_native_fixture_keeps_all_original_checks(self):
        # Software fixture checks the audit, not DUT correctness. It includes
        # all 13 writers and 15 stores; no unknown/whole-destination skips.
        activities, mapping, rows = self.fixture()
        result = repair.native_state(self.reference, activities, mapping,
                                     self.pre['symbols'], rows)
        self.assertEqual(result['primary_writers'], 13)
        self.assertEqual(result['defined_mask_bits'], 192)
        self.assertEqual(result['mask_tail_bits_checked'], 2880)
        self.assertEqual(result['unknown_active_bytes_skipped'], 0)
        self.assertFalse(result['whole_destination_skipped'])

    def test_incorrect_FPU_producer_on_integer_ALU_rejected(self):
        activities, mapping, rows = self.fixture()
        seq = next(s for s, i in mapping.items()
                   if self.reference[i].pc == self.pre['symbols']['mc_clear24'])
        activities[seq].writes[0] = replace(activities[seq].writes[0], source=1)
        with self.assertRaisesRegex(Exception, 'Exact writer producer'):
            repair.native_state(self.reference, activities, mapping, self.pre['symbols'], rows)

    def test_native_mutations_remain_rejected(self):
        for field, value in (('known_be', 0), ('be', 0), ('arch_seq', 9999),
                             ('source', 1), ('data', 0), ('addr', 8)):
            activities, mapping, rows = self.fixture()
            seq = next(s for s, i in mapping.items()
                       if self.reference[i].pc == self.pre['symbols']['mc_compare'])
            activities[seq].writes[0] = replace(activities[seq].writes[0], **{field: value})
            with self.subTest(field=field):
                with self.assertRaises(Exception):
                    repair.native_state(self.reference, activities, mapping,
                                        self.pre['symbols'], rows)

    def test_missing_evidence_cannot_pass(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(Exception, 'Missing or empty'):
                repair.audit(Path(empty))

    def test_reference_is_independent_of_old_RTL_and_coverage(self):
        self.assertFalse(any('/hardware/' in path or '.vdb/' in path
                             for path in self.reference_pins))
        self.assertEqual(self.reference_pins[str(self.c.runner.ELF)],
                         self.c.runner.ELF_SHA)
        self.assertIn(self.pre['reference'], self.reference_pins)

    def test_no_frozen_runner_or_coverage_admission_called(self):
        with patch.object(self.c.runner, 'prepare', side_effect=AssertionError('old image')):
            with patch.object(self.c.runner, 'preflight', side_effect=AssertionError('old RTL')):
                with patch.object(self.c, 'raw_gain', side_effect=AssertionError('old coverage')):
                    with self.assertRaisesRegex(Exception, 'Simulator/UVM failure'):
                        repair.audit(self.failed)


if __name__ == '__main__':
    unittest.main()
