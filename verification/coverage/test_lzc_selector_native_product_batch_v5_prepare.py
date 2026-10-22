"""Prepared temporary smoke/full successor contracts; no licensed tool invocation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import lzc_selector_native_product_batch_v5_prepare as v5

OUT = v5.batch.product.OUT
PREVIOUS = OUT / 'lzc_selector_native_product_batch-707-20261006-04'
REVIEW = OUT / 'lzc_selector_native_product_batch-707-20261006-04-independent-review-01'


class V5PrepareTests(unittest.TestCase):
    def test_actual_script_dependency_chain_has_no_expansion(self):
        files = [v5.FULL, v5.LIBRARY, v5.PROBE, v5.GUARD, v5.v4.v3.visibility.SCRIPT,
                 v5.batch.SCRIPT, v5.HERE / 'lzc_selector_native_product_discover.tcl']
        pins = v5.dependency_scan(files)
        self.assertEqual(len(pins), 7)
        self.assertNotIn(str(v5.v4.SCRIPT), pins)
        self.assertNotIn(str(v5.v4.v3.SCRIPT), pins)
        self.assertIn('eval [linsert $args 0 gui_exclude_items]', v5.PROBE.read_text())
        self.assertIn('gui_exclusion -reset', v5.PROBE.read_text())

    def test_parser_preflight_failure_stops_before_load(self):
        body = 'set lpq_test_only 1\nsource {' + str(v5.PROBE) + r'''}
set loads 0
proc gui_open_cov {args} {incr ::loads}
proc lpn_guard_exclude {args} {error {extra characters after close-brace}}
lpd_require [catch {lpq_session} message] "Probe accepted parser failure"
lpd_require [expr {$message eq "Guard parser/preflight failed before design load" && $loads == 0 && !$lpn_global_before_complete}] "Failure did not stop before load"
'''
        wrapped = 'if {[catch {\n' + body + '\n} message]} {puts stderr "$message\n$::errorInfo"; exit 1}\n'
        result = subprocess.run(['tclsh'], input=wrapped, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prepare_preserves_full1204200_and_separates_temporary_smoke84(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_v5_full_unit-') as a, \
             tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_v5_probe_unit-') as b:
            output, probe = Path(a), Path(b)
            output.rmdir()
            probe.rmdir()
            with mock.patch.object(v5.subprocess, 'Popen') as launch:
                v5.prepare(PREVIOUS, REVIEW, output, probe)
                plan, full = v5.reviewed_probe(probe)
                launch.assert_not_called()
            old = json.loads((PREVIOUS / 'batch-plan.json').read_bytes())
            self.assertEqual(full['targets'], old['targets'])
            self.assertEqual(full['protection_rows'], old['protection_rows'])
            self.assertEqual(full['command'][2], '10500s')
            self.assertEqual(plan['command'][2], '900s')
            self.assertEqual(plan['positions'], 84)
            self.assertEqual(plan['same_session_scope_audits'], 5)
            self.assertTrue(plan['qualification_gate_remains_closed'])
            self.assertTrue(plan['historical_baseline_context_only'])
            self.assertTrue(plan['capture'])
            self.assertTrue(plan['exclusion'])
            self.assertEqual(plan['temporary_singleton_points'], 1)
            self.assertTrue(plan['final_reset_required'])
            self.assertFalse(plan['global4200_fresh_audit'])
            self.assertFalse((probe / 'reviewed-start.json').exists())
            self.assertEqual((output / 'native-bindings.tcl').read_bytes(), (PREVIOUS / 'native-bindings.tcl').read_bytes())
            self.assertEqual((output / 'guarded-session.tcl').read_bytes(), (PREVIOUS / 'guarded-session.tcl').read_bytes())
            self.assertEqual((output / 'selection.tcl').read_text().partition('\n')[2],
                             (PREVIOUS / 'selection.tcl').read_text().partition('\n')[2])
            plan['capture'] = False
            (probe / 'smoke-plan.json').write_text(json.dumps(plan))
            (probe / 'smoke-plan.sha256.json').write_text(json.dumps({
                str(probe / 'smoke-plan.json'): v5.sha(probe / 'smoke-plan.json')}))
            with self.assertRaises(ValueError):
                v5.reviewed_probe(probe)

    def test_probe_verifier_refuses_full_qualification_marker(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_v5_verify_unit-') as temp:
            output = Path(temp)
            (output / 'DVEfiles').mkdir()
            (output / 'DVEfiles/dve_gui.log').write_text(
                'LZC_NATIVE_GUARD_SMOKE_COMPLETE_PENDING_OFFLINE_VERIFICATION_NOT_QUALIFICATION\n'
                'LZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE\n')
            with self.assertRaises(ValueError):
                v5.verify_probe(output, {}, {})


if __name__ == '__main__':
    unittest.main()
