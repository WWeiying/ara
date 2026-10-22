import copy
import inspect
import json
from pathlib import Path
import subprocess
import tempfile
import textwrap
from types import FunctionType, SimpleNamespace
import unittest
from unittest.mock import patch

import report_diagnostic_combo745 as report
import test_report_native_combo745 as prior_tests


class DiagnosticComboTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = report.life.read_bound(report.DEFAULT_PRIOR / 'config.json', report.PRIOR_CONFIG_SHA)
        cls.config['diagnostic_config'] = json.loads((report.NATIVE / 'config.json').read_bytes())
        cls.text = (report.DEFAULT_PRIOR / 'combined.el').read_text() + (report.NATIVE / 'first.el').read_text()

    def test_actual_native_whole_union_and_prior_preserved(self):
        parsed = report.records(self.text, self.config)
        self.assertEqual(parsed['prior'], self.config['expected_union'])
        self.assertEqual(len(parsed['diagnostic']), 11038)

    def test_duplicate_diagnostic_direction_rejected(self):
        with self.assertRaises(ValueError):
            report.records(self.text + (report.NATIVE / 'first.el').read_text(), self.config)

    def test_product_snapshot_not_substitutable(self):
        text = self.text.replace('gen_akv_integration_assertions.akv_consumed_request_q.', 'pe_req_i.')
        with self.assertRaises(ValueError):
            report.records(text, self.config)

    def test_native_foreign_checksum_rejected(self):
        native = (report.NATIVE / 'first.el').read_text()
        native = native.replace('CHECKSUM: "', 'CHECKSUM: "foreign ', 1)
        with self.assertRaises(ValueError):
            report.records((report.DEFAULT_PRIOR / 'combined.el').read_text() + native, self.config)

    def test_same_scope_mixed_metric_block_routes_by_field(self):
        # A diagnostic block and a prior block may legally share a scope. A non-Toggle
        # metric must stay in the substantive prior verifier, never diagnostic grammar.
        native = (report.NATIVE / 'first.el').read_text()
        native += '\nCHECKSUM: "1"\nINSTANCE: ' + self.config['diagnostic_config']['instances'][0]['scope'] + '\nBranch invalid\n'
        with self.assertRaises(ValueError):
            report.records((report.DEFAULT_PRIOR / 'combined.el').read_text() + native, self.config)

    def test_no_prepare_directory_created_before_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'not-created'
            with patch.object(report.life, 'OUT', Path(tmp)), patch.object(report, 'qualified_prior',
                    side_effect=ValueError('Wait for exact prior745 qualification')):
                with self.assertRaisesRegex(ValueError, 'Wait for exact prior745'):
                    report.prepare(out, report.DEFAULT_PRIOR, '0' * 64)
            self.assertFalse(out.exists())

    def test_foreign_predecessor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Wait for exact prior745'):
            report.qualified_prior(Path('/foreign'), '0' * 64)

    def test_verify_rebinds_substantive_core_not_v3_wrapper(self):
        config = dict(self.config, diagnostic_references=[])
        def capture_function(code, namespace):
            self.assertIs(code, report.prior.verify.__code__)
            self.assertIs(namespace['old'].verify, report.prior.inherited.original_verify)
            self.assertIsNot(namespace['old'].verify, report.prior.old.verify)
            self.assertIs(namespace['records'], report.records)
            self.assertEqual(namespace['__file__'], report.__file__)
            return lambda *args: None
        with patch.object(report, 'check', return_value=config), patch.object(report, 'FunctionType', capture_function):
            report.verify(Path('/unused'), 'seal')

    def test_real_tcl_hook_one_load_and_all_old_new_five_stage_files(self):
        # Reuse the fully read745 GUI stub, executing both real hooks and audits.
        proxy = SimpleNamespace(TCL=report.TCL, HERE=report.HERE,
                                STAGES=report.prior.STAGES, dict_rows=report.prior.dict_rows)
        namespace = dict(prior_tests.__dict__, report=proxy)
        original_write, original_read = Path.write_text, Path.read_text
        stages = set()
        def write(path, text, *args, **kwargs):
            if path.name == 'selection.tcl':
                text += 'set diagnostic_instances [list [list ara_tb.queue [list data]]]\n'
            return original_write(path, text, *args, **kwargs)
        def read(path, *args, **kwargs):
            if path.name.startswith('native_') and path.suffix == '.tsv':
                stage = path.name.split('_')[1]
                self.assertIn('data', original_read(path.with_name('diagnostic_' + stage + '_0.tsv')))
                stages.add(stage)
            return original_read(path, *args, **kwargs)
        function = FunctionType(prior_tests.HookTests.test_actual_proc_import_and_full_hook_five_stages.__code__, namespace)
        with patch.object(Path, 'write_text', write), patch.object(Path, 'read_text', read):
            function(self)
        self.assertEqual(stages, {'before', 'selected', 'reset', 'reloaded', 'final'})


if __name__ == '__main__':
    unittest.main()
