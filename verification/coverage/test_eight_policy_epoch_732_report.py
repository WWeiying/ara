import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import eight_policy_epoch_732_report as report
from verification_epoch import EpochError


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.output = self.parent / 'report'
        self.output.mkdir()

    def populate(self):
        with patch.object(report, 'OUT', self.parent):
            for path in report.generated_catalog(self.output):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'')

    def test_catalog_exact_scope_and_source_disjoint(self):
        self.populate()
        with patch.object(report, 'OUT', self.parent):
            paths = report.generated_catalog(self.output)
            self.assertEqual(len(paths), len(set(paths)))
            self.assertNotIn(self.output / 'config.json', paths)
            self.assertNotIn(self.output / 'status.json', paths)
            self.assertNotIn(self.output / 'capture-result.json', paths)
            self.assertIn(self.output / 'snapshot/states_after-root.csv', paths)
            pins = report.capture_generated(self.output, {})
            self.assertEqual(set(pins), {str(p) for p in paths})
            with self.assertRaises(EpochError):
                report.capture_generated(self.output, pins)

    def test_missing_generated_file_rejected(self):
        with patch.object(report, 'OUT', self.parent):
            with self.assertRaises(EpochError):
                report.capture_generated(self.output, {})

    def test_symlink_leaf_or_parent_rejected(self):
        self.populate()
        path = self.output / 'applied.el'
        path.unlink()
        target = self.parent / 'other'
        target.write_bytes(b'')
        path.symlink_to(target)
        with patch.object(report, 'OUT', self.parent):
            with self.assertRaises(EpochError):
                report.capture_generated(self.output, {})

    def test_generated_hash_is_observation_not_approval(self):
        self.populate()
        path = self.output / 'applied.el'
        path.write_bytes(b'INVALID_NATIVE_NOT_APPROVED')
        with patch.object(report, 'OUT', self.parent):
            pins = report.capture_generated(self.output, {})
        self.assertEqual(pins[str(path)], hashlib.sha256(path.read_bytes()).hexdigest())
        # capture_generated has no approval result. The full original verifier
        # is mandatory in check(..., generated=True), not bypassed by hashing.
        self.assertIsInstance(pins[str(path)], str)

    def test_symlink_parent_rejected(self):
        self.populate()
        directory = self.output / 'DVEfiles'
        (directory / 'dve_gui.log').unlink()
        directory.rmdir()
        alternate = self.parent / 'alternate'
        alternate.mkdir()
        (alternate / 'dve_gui.log').write_bytes(b'')
        directory.symlink_to(alternate, target_is_directory=True)
        with patch.object(report, 'OUT', self.parent):
            with self.assertRaises(EpochError):
                report.capture_generated(self.output, {})

    def test_generated_mutation_changes_observed_authority(self):
        self.populate()
        with patch.object(report, 'OUT', self.parent):
            before = report.capture_generated(self.output, {})
            (self.output / 'summary_applied.csv').write_bytes(b'altered')
            self.assertNotEqual(before, report.capture_generated(self.output, {}))

    def test_once_claim_preserved(self):
        path = self.output / 'epoch-launch-claim.json'
        report.save(path, {'claim': True})
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            report.save(path, {'claim': False})
        self.assertEqual(path.read_bytes(), original)

    def test_wrong_seal_rejected(self):
        path = self.output / report.PLAN
        path.write_text('{}')
        with self.assertRaises(EpochError):
            report.check(self.output, '0' * 64)

    def test_live_procfs_attestation_not_routed_to_source_epoch(self):
        original = report.wiring.lifecycle.tool
        owner = SimpleNamespace(tool=SimpleNamespace(revalidate=lambda record: None))
        actual = report.runtime_tool(owner)
        self.assertIs(actual.verify_live_executable, original.verify_live_executable)
        self.assertIs(actual.verify_launch_child, original.verify_launch_child)
        self.assertEqual(actual.process_info(os.getpid()), original.process_info(os.getpid()))

    def test_preparation_context_exact732_complete_original_checker(self):
        context, _ = report.preparation_context()
        self.assertEqual(context.population, 732)
        self.assertIs(context.check_config.__func__.__code__,
                      report.wiring.population.Context.check_config.__code__)

    def test_bad_plan_schema_rejected_before_reader(self):
        path = self.output / report.PLAN
        path.write_text(json.dumps({'schema': 'ARBITRARY733'}))
        seal = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(EpochError):
            report.check(self.output, seal)


if __name__ == '__main__':
    unittest.main()
