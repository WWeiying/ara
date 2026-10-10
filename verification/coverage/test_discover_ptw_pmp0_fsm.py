from pathlib import Path
import subprocess
import tempfile
import unittest

import discover_ptw_pmp0_fsm as m


class DiscoveryTests(unittest.TestCase):
    def test_sealed_plan_exact_sample_and_no_selectors(self):
        plan = m.load_plan({})
        self.assertEqual((plan['targets'], plan['protected'], plan['selected_test_count']), (4, 31, 1))
        self.assertTrue(all(r['native_selector'] is None for r in plan['rows']))

    def test_no_mutating_coverage_api(self):
        text = m.HOOK.read_text()
        self.assertNotIn('gui_exclusion', text)
        self.assertNotIn('gui_cov_excl_review', text)
        self.assertNotIn('gui_exclude', text)
        self.assertNotIn('.el', text)

    def test_real_tcl_query_errors_retained_and_global_source(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'selection.tcl').write_text('set pmp4_design DESIGN\nset pmp4_test_vdb SAMPLE\nset pmp4_test EXACTTEST\nset pmp4_scope EXACTSCOPE\n')
            (root / 'live-ready').write_text('verified\n')
            (root / 'DVEfiles').mkdir()
            (root / 'DVEfiles/dve_gui.log').write_text("The design 'DESIGN' was loaded successfully.\n")
            prefix = 'set env(DVE_COVERAGE_OUTPUT) {%s}\n' % root
            prefix += '''
proc gui_open_cov {args} {if {$args ne {-hier DESIGN -testdir SAMPLE -test EXACTTEST -merge PTWPMP4ReadOnly}} {error BAD_INPUTS}}
proc help {args} {return HELP}
proc gui_get_window_ids {} {return CoverageTable.1}
proc gui_list_expand {args} {}
proc gui_list_action {args} {if {[lindex $args end] ne "EXACTSCOPE"} {error BAD_SCOPE}}
proc gui_covdetail_query {args} {return FSM}
proc gui_list_get_selected {args} {return state_q}
proc gui_list_select {args} {}
proc gui_list_get_meta {args} {error UNSUPPORTED_META}
proc gui_list_get_value {args} {error UNSUPPORTED_VALUE}
proc gui_list_get {args} {return 17}
proc gui_exit {args} {}
'''
            result = subprocess.run(['tclsh'], input=prefix + m.HOOK.read_text(), text=True, capture_output=True, check=True)
            self.assertEqual(result.stderr, '')
            self.assertIn('PTW_FSM_READONLY_DISCOVERY_DONE', result.stdout)
            observations = (root / 'native-observations.tsv').read_text()
            self.assertIn('UNSUPPORTED_META', observations)
            self.assertIn('RESULT\t1', observations)
            self.assertEqual((root / 'selected_tests.txt').read_text(), 'EXACTTEST\n')

    def test_real_tcl_load_failure_before_getters(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'selection.tcl').write_text('set pmp4_design DESIGN\nset pmp4_test_vdb SAMPLE\nset pmp4_test EXACTTEST\nset pmp4_scope EXACTSCOPE\n')
            (root / 'live-ready').write_text('verified\n')
            (root / 'DVEfiles').mkdir()
            (root / 'DVEfiles/dve_gui.log').write_text("The design 'DESIGN' was loaded successfully.\nEK-CMD-015 badpath\n")
            prefix = 'set env(DVE_COVERAGE_OUTPUT) {%s}\nproc gui_open_cov {args} {}\nproc gui_exit {args} {}\n' % root
            result = subprocess.run(['tclsh'], input=prefix + m.HOOK.read_text(), text=True, capture_output=True, check=True)
            self.assertIn('Coverage load failed', result.stdout)
            self.assertFalse((root / 'native-api.txt').exists())
            self.assertFalse((root / 'selected_tests.txt').exists())


if __name__ == '__main__':
    unittest.main()
