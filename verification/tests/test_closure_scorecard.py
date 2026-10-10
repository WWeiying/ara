import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'coverage/closure_scorecard.py'
spec = importlib.util.spec_from_file_location('closure_scorecard', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScorecardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dve = self.root / 'combined-dve'
        self.dve.mkdir()
        self.csv = self.dve / 'summary.csv'
        with self.csv.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['Name', 'Depth', *module.METRICS])
            writer.writeheader()
            scopes = set()
            for scope in module.EXPECTED_SCOPES:
                parts = scope.split('.')
                scopes.update('.'.join(parts[:i]) for i in range(1, len(parts) + 1))
            for scope in sorted(scopes):
                name, depth = scope.rsplit('.', 1)[-1], scope.count('.')
                writer.writerow(dict(Name=name, Depth=depth, **{m: '91.00%' for m in module.METRICS}))
        ledger = [dict(name='one', vdb='/one.vdb', status='PASS', passed_only=True,
                       vdb_valid=True, reused=False, coverage_test='one')]
        self.write('all-passed-outcomes.json', ledger)
        self.write('combined-bits.json', dict(tests=['/one.vdb']))
        (self.dve / 'inputs.txt').write_text('/compile.vdb\n/one.vdb\n')
        (self.dve / 'selected_tests.txt').write_text('/one/one\n')
        self.write('combined-dve/waiver_status.json', dict(status='NOT_APPLICABLE_UNREVIEWED_DESIGN'))
        self.write('checkpoint.json', dict(coverage_status='COMPLETE', aggregate_passed=1))
        self.reseal()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def reseal(self):
        paths = [self.csv, self.root / 'all-passed-outcomes.json', self.root / 'combined-bits.json',
                 self.dve / 'inputs.txt', self.dve / 'waiver_status.json']
        paths.append(self.dve / 'selected_tests.txt')
        self.write('collection.json', dict(status='PASS', passed=1,
            reports={str(p): module.digest(p) for p in paths}))

    def test_completed_thresholds(self):
        report = module.scorecard(self.root)
        self.assertEqual(report['status'], 'TARGET_MET_RAW')
        self.assertEqual(len(report['modules']), len(module.EXPECTED_SCOPES))
        self.assertIn('Threshold attainment is not', module.markdown(report))

    def test_low_fsm_is_open_and_na_is_not_coverage(self):
        text = self.csv.read_text().replace('91.00%,91.00%,91.00%,91.00%,91.00%',
                                          '91.00%,91.00%,91.00%,53.00%,NA')
        self.csv.write_text(text)
        self.reseal()
        report = module.scorecard(self.root)
        self.assertEqual(report['status'], 'OPEN')
        self.assertEqual(report['modules'][0]['gap_percentage_points']['FSM'], 37)
        self.assertIsNone(report['modules'][0]['raw']['Toggle'])

    def test_unfinished_aggregate_rejected(self):
        self.write('checkpoint.json', dict(coverage_status='PENDING', aggregate_passed=1))
        with self.assertRaisesRegex(ValueError, 'not completed'):
            module.scorecard(self.root)

    def test_hash_drift_rejected(self):
        self.csv.write_text(self.csv.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'report drift'):
            module.scorecard(self.root)

    def test_failed_ledger_even_if_resealed_rejected(self):
        self.write('all-passed-outcomes.json', [dict(name='one', vdb='/one.vdb', status='FAIL',
                   passed_only=True, vdb_valid=True, reused=False)])
        self.reseal()
        with self.assertRaisesRegex(ValueError, 'unverified'):
            module.scorecard(self.root)

    def test_membership_drift_rejected(self):
        self.write('combined-bits.json', dict(tests=['/foreign.vdb']))
        self.reseal()
        with self.assertRaisesRegex(ValueError, 'membership'):
            module.scorecard(self.root)

    def test_missing_module_rejected(self):
        self.csv.write_text('\n'.join(self.csv.read_text().splitlines()[:-1]) + '\n')
        self.reseal()
        with self.assertRaisesRegex(ValueError, 'critical module'):
            module.scorecard(self.root)

    def test_all_na_does_not_pass(self):
        self.csv.write_text(self.csv.read_text().replace('91.00%', 'NA'))
        self.reseal()
        report = module.scorecard(self.root)
        self.assertEqual(report['status'], 'OPEN')
        self.assertTrue(all(not r['raw_target_met'] for r in report['modules']))

    def test_missing_lane_rejected_even_if_other_queues_present(self):
        text = self.csv.read_text()
        self.csv.write_text('\n'.join(l for l in text.splitlines()
                           if 'gen_lanes[3]' not in l) + '\n')
        self.reseal()
        with self.assertRaises(ValueError):
            module.scorecard(self.root)

    def test_selected_test_drift(self):
        (self.dve / 'selected_tests.txt').write_text('/foreign/test\n')
        with self.assertRaisesRegex(ValueError, 'report drift'):
            module.scorecard(self.root)
        self.reseal()
        with self.assertRaisesRegex(ValueError, 'selected-test membership'):
            module.scorecard(self.root)

    def test_foreign_recovery_receipt_rejected(self):
        recovery = self.root / 'receipt'
        recovery.mkdir()
        data = dict(schema='gap65-report-only-recovery-v1', status='PASS',
                    source_runtime='/foreign', aggregate_passed=651,
                    original_evidence_modified=False, files={})
        (recovery / 'completion.json').write_text(json.dumps(data))
        (recovery / 'checkpoint.json').write_text(json.dumps(dict(
            completion_sha256=module.digest(recovery / 'completion.json'),
            coverage_status='COMPLETE', aggregate_passed=651)))
        with self.assertRaisesRegex(ValueError, 'foreign/unbound'):
            module.scorecard(self.root, recovery)


if __name__ == '__main__':
    unittest.main()
