import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import prepare_six_policy_population as subject


class PopulationTests(unittest.TestCase):
    def fixture(self):
        directory = subject.frozen.OUT / 'gap103-offline-admitted-720-20261006-01'
        return (json.loads((directory / 'combined-bits.json').read_text()),
                json.loads((directory / 'status.json').read_text()),
                (directory / 'combined-inputs.txt').read_text().splitlines())

    def test_real720_admission_membership(self):
        subject.validate_population(*self.fixture(), 720)

    def test_wrong_population_duplicate_and_order_rejected(self):
        bits, status, inputs = self.fixture()
        with self.assertRaises(ValueError):
            subject.validate_population(bits, status, inputs, 721)
        broken = copy.deepcopy(bits)
        broken['tests'][-1] = broken['tests'][0]
        with self.assertRaises(ValueError):
            subject.validate_population(broken, status, inputs, 720)
        with self.assertRaises(ValueError):
            subject.validate_population(bits, status, inputs[::-1], 720)

    def test_failure_timeout_candidate_not_admitted(self):
        bits, status, inputs = self.fixture()
        for value in ('FAIL', 'TIMEOUT', 'FULL_ORIGINAL_ORACLE_PASS_NOT_ADMITTED'):
            with self.assertRaises(ValueError):
                subject.validate_population(bits, dict(status, status=value), inputs, 720)

    def test_private_review_only_one_population_constant_changes(self):
        original = subject.frozen.latest_review.__code__
        for population in (720, 721, 722):
            changed = subject.review_function(population, lambda p: '').__code__
            self.assertEqual(changed.co_code, original.co_code)
            self.assertEqual(sum(a != b for a, b in zip(original.co_consts, changed.co_consts)), 1)
        for population in (True, 716, '721'):
            with self.assertRaises(ValueError):
                subject.review_function(population, lambda p: '')

    def test_current_dispatcher_never_hashed(self):
        ctx = subject.Context(subject.frozen.OUT / 'admission-fixture', '0' * 64, 721)
        with patch.object(subject.frozen, 'sha', return_value=subject.snapshot.SNAPSHOT_SHA) as digest:
            ctx.digest(subject.snapshot.HARDWARE_PATH)
            digest.assert_called_once_with(str(subject.snapshot.SNAPSHOT))

    def test_snapshot_wrong_expected_bytes_rejected(self):
        ctx = subject.Context(subject.frozen.OUT / 'admission-fixture', '0' * 64, 721)
        with self.assertRaises(ValueError):
            ctx.pin({}, subject.snapshot.HARDWARE_PATH, '0' * 64)

    def test_tcl_is_narrow_successor_not_new_exclusions(self):
        old = subject.frozen.TCL.read_text()
        expected = old.replace('global env exp1272_library_only pack208_library_only six_expected_count',
                               'global env exp1272_library_only pack208_library_only six_expected_count six_admission_count', 1)
        expected = expected.replace('if {$six_expected_count != 717} {error "Unreviewed explicit population"}',
            'if {![string is integer -strict $six_expected_count] || $six_expected_count < 717 || $six_expected_count != $six_admission_count} {\n        error "Unreviewed explicit sealed population"\n    }', 1)
        expected = expected.replace('SIX717_SELECTION_ADAPTER_INSTALLED', 'SIX_POPULATION_SELECTION_ADAPTER_INSTALLED')
        self.assertEqual(subject.TCL.read_text().partition('\n')[2], expected.partition('\n')[2])
        self.assertNotIn('{*}', subject.TCL.read_text())

    def test_no_launch_entry(self):
        with self.assertRaises(SystemExit):
            subject.main(['run', '--output', str(subject.frozen.OUT / 'never-launched')])


if __name__ == '__main__':
    unittest.main()
