from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import c910_srt_datapath_native_v3 as v3


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        review = v3.base.life.read_bound(v3.base.REVIEW, v3.base.REVIEW_SHA)
        cls.config = dict(instances=v3.base.instances(review))

    def calibration(self, kind='reg'):
        first = self.config['instances'][0]
        return 'CHECKSUM: "%s %s"\nINSTANCE: %s\nToggle cur_rem "%s cur_rem[60:0]"\n' % (
            first['design_module_checksum'], first['toggle_checksum'], first['scope'], kind)

    def test_reg_and_logic_measured_types(self):
        for kind in ('reg', 'logic'):
            self.assertEqual(v3.calibration_kind(self.calibration(kind), self.config), kind)
            text = v3.candidate_text(self.config, kind)
            self.assertEqual(len(v3.base.parse_el(text, self.config)), 1264)
            self.assertNotIn('Toggle bound_sel ', text)
            self.assertNotIn('Toggle digit_bound1 ', text)

    def test_source_kind_not_assumed_logic(self):
        text = v3.candidate_text(self.config, 'reg')
        self.assertIn('Toggle cur_rem "reg cur_rem[60:0]"', text)
        self.assertIn('"wire ', text)
        self.assertNotIn('"logic ', text)

    def test_calibration_rejects_wrong_checksum_bounds_type_extra(self):
        text = self.calibration()
        for wrong in (text.replace('3969040510', '0'), text.replace('[60:0]', '[59:0]'),
                      text.replace('"reg ', '"wire '), text + text,
                      text + 'MODULE: injected\n'):
            with self.assertRaises(ValueError):
                v3.calibration_kind(wrong, self.config)

    def test_candidate_rejects_unmeasured_type(self):
        with self.assertRaises(ValueError):
            v3.candidate_text(self.config, 'wire')

    def test_error_artifact_blocks_even_before_config_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'error.txt').touch()
            with self.assertRaisesRegex(ValueError, 'error artifact'):
                v3.verify(out, '0' * 64)

    def test_prepare_writes_final_config_once_with_reference_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'fresh'

            def prepare(path):
                path.mkdir()
                v3.base.life.save(path / 'config.json', dict(pins={}))

            save = v3.base.life.save
            with patch.object(v3, 'original_prepare', prepare):
                v3.prepare(out)
            config = v3.base.json.loads((out / 'config.json').read_bytes())
            self.assertEqual(config['method'],
                             'ONE_REG_NATIVE_CALIBRATION_THEN_EXACT_CANDIDATE_LOAD')
            self.assertIn(str(v3.base.life.OUT /
                              'fma-datapath-108-native-agent-20261007-02/first.el'),
                          config['pins'])
            self.assertIs(v3.base.life.save, save)

    def tcl(self, body):
        script = 'set ::c910_test_only 1\nsource {%s}\n' % v3.base.TCL
        script += 'proc fma_need {ok why} {if {!$ok} {error $why}}\n' + body
        result = subprocess.run(['tclsh'], input=script, text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout.strip()

    def test_nested_actual_old_selection_is_individually_unselected(self):
        result = self.tcl(r'''
set ::selected [list [list {bound_sel[6:0]}]]
set ::cancelled {}
proc gui_list_get_selected {args} {
    if {[lindex $args end] eq "-count"} {return [llength $::selected]}
    return $::selected
}
proc gui_list_select {args} {
    set values [lindex $args end]
    if {[lindex $args end-1] eq "-unselect"} {
        if {$values ne [list {bound_sel[6:0]}]} {error BAD_NATIVE_TOKEN}
        lappend ::cancelled [lindex $values 0]
        set ::selected {}
    } else {set ::selected [list $values]}
}
c910_select [list {cur_rem[60:0]} {cur_rem[60:0]} {cur_rem[60:0]}]
puts $::cancelled
''')
        self.assertEqual(result, '{bound_sel[6:0]}')

    def test_reset_recalculate_then_save_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.tcl('set ::env(DVE_COVERAGE_OUTPUT) {%s}\n' % tmp + r'''
set ::calls {}
proc gui_exclusion {args} {lappend ::calls [lindex $args end]}
proc gui_process_events {args} {lappend ::calls events}
proc fma_save {name} {lappend ::calls $name}
c910_failure ORIGINAL_ERROR DETAILS
puts $::calls
''')
            self.assertIn('-reset -recalculate events cleanup-empty.el', result)
            self.assertEqual((Path(tmp) / 'error.txt').read_text(), 'ORIGINAL_ERROR\nDETAILS\n')

    def test_failed_recalculation_never_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.tcl('set ::env(DVE_COVERAGE_OUTPUT) {%s}\n' % tmp + r'''
proc gui_exclusion {args} {if {[lindex $args end] eq "-recalculate"} {error RECALC_FAILED}}
proc fma_save {name} {error SHOULD_NOT_SAVE}
c910_failure ORIGINAL_ERROR DETAILS
puts [read [set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] r]]]
close $stream
''')
            self.assertIn('CLEANUP_FAILED RECALC_FAILED', result)
            self.assertNotIn('SHOULD_NOT_SAVE', result)

    def test_batch_uses_load_not_per_target_clicks(self):
        text = v3.base.TCL.read_text()
        self.assertEqual(text.count('c910_select [lindex $calibration 0]'), 1)
        self.assertNotIn('fma_select $row', text)
        self.assertIn('c910_load candidate.el', text)
        self.assertIn('c910_load first.el', text)
        self.assertIn('fma_python fma_helper c910_fma_tcl', text)


if __name__ == '__main__':
    unittest.main()
