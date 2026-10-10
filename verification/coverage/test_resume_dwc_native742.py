"""Full Tcl session fixture and immutable actual-native per-direction evidence."""
import shutil
import tempfile
from pathlib import Path
import tkinter
import unittest
import resume_dwc_native742 as r


class ResumeTests(unittest.TestCase):
    def test_actual168_and31(self):
        c = r.predecessor.inventory(r.b.json.loads(r.b.REVIEW.read_bytes()))
        records = r.predecessor.parse_el((r.predecessor.FAILED / 'first.el').read_text(), c)
        self.assertEqual(sum(x[0] == 'tgl' for x in records), 168)
        self.assertEqual(sum(x[0] == 'fsm' for x in records), 31)

    def test_complete_session_global_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            shutil.copyfile(r.b.life.OUT / 'dwc31-fsm168-toggle-native742-agent-20261007-02/selection.tcl', out / 'selection.tcl')
            (out / 'live-ready').touch()
            t = tkinter.Tcl()
            t.setvar('env(DVE_COVERAGE_OUTPUT)', directory)
            t.setvar('dw_resume_test_only', 1)
            t.call('source', str(r.b.TCL))
            t.eval('''
                set observed {}
                proc gui_open_cov {args} {}
                proc dw_save {name args} {lappend ::observed [list save $name]}
                proc dw_load {name} {lappend ::observed [list load $name]}
                proc dw_reset {} {lappend ::observed reset}
                proc exec {args} {return {HOST_EL_VALIDATION_STUB}}
                proc dw_audit {stage active} {
                    global dw_groups dw_toggles observed
                    if {[llength $dw_groups] != 4 || [llength $dw_toggles] != 3} {error bad_global_selection}
                    lappend observed [list audit $stage $active]
                }
            ''')
            # Actual v2 failure: sourcing in dw_session without global groups leaves audit unbound.
            t.eval('unset dw_groups; unset dw_toggles')
            with self.assertRaises(tkinter.TclError): t.call('dw_session')
            t.call('source', str(out / 'selection.tcl'))
            t.eval('set observed {}')
            t.call('dw_session')
            expected = '{save initial-empty.el} {audit before 0} {load candidate.el} {audit selected 1} {save first.el} reset {audit reset 0} {save reset-empty.el} {load first.el} {audit reloaded 1} {save second.el} reset {audit final 0} {save final-empty.el}'
            self.assertEqual(t.eval('set observed'), expected)

    def test_no_repeat_selection(self):
        body = r.b.TCL.read_text()
        self.assertNotIn('gui_exclude_items', body)
        self.assertIn('source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]', body)


if __name__ == '__main__': unittest.main()
