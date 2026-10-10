import inspect
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_rvh_branch_full_empty_v2 as subject
import test_capture_rvh_branch_full_726 as full_tests


STUB = r'''
set current {}
set oldraw {}
set afterraw AUTO
set unselected {}
set selected {}
proc gui_list_get_selected {args} {
    if {$::current eq ""} {return $::oldraw}
    if {$::afterraw ne "AUTO"} {return $::afterraw}
    return [list $::current]
}
proc gui_list_select {args} {
    set tokens [lindex $args end]
    foreach token $tokens {
        if {$token eq ""} {error {gui_list_select: List item(s) given by ""  were not found.}}
        if {$token eq "Branch99.9"} {error "native item not found"}
    }
    if {[lsearch -exact $args -unselect] >= 0} {
        set ::unselected $tokens;set ::current {};return
    }
    set ::selected $tokens;set ::current [lindex $tokens 0]
}
'''


class EmptySelectionTests(unittest.TestCase):
    def tcl(self, body, adapter=True):
        script='set dbg_library_only 1\nsource {%s}\n' % (subject.frozen.HERE/'capture_operand_debug.tcl')
        if adapter:
            script+='source {%s}\n' % subject.SELECTION
        script+=STUB+'\n'+body+'\n'
        result=subprocess.run(['/usr/bin/tclsh'], input=script, text=True, capture_output=True, check=True)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_actual_failure_fixture_dtlb_first_selection_not_itlb(self):
        log=(subject.FAILED/'DVEfiles/dve_gui.log').read_text()
        before=(subject.FAILED/'states_before.tsv').read_text().splitlines()[1:]
        scopes=[line.split('\t')[0] for line in before]
        self.assertEqual(len(before),870)
        self.assertTrue(scopes[-1].endswith('i_cva6_mmu'))
        self.assertFalse(any(scope.endswith('i_dtlb') for scope in scopes))
        self.assertIn('i_cva6_mmu.i_dtlb 2\nRVH_FULL_ERROR gui_list_select: List item(s) given by ""',log)
        self.assertNotIn('i_itlb',log)
        # Old raw value was not logged; this reproduces, but does not claim it was captured.
        out=self.tcl('set oldraw [list ""]\nputs [catch {dbg_select branch Branch0.0} msg]\nputs $msg',False)
        self.assertIn('1\ngui_list_select: List item(s) given by ""',out)

    def test_empty_list_and_single_empty_token_no_unselect(self):
        for value in ('{}','[list ""]','[list "" ""]'):
            with self.subTest(value=value):
                out=self.tcl('set oldraw %s\ndbg_select branch Branch0.0\nputs "OK=$selected UNSELECT=$unselected"' % value)
                self.assertIn('OK=Branch0.0 UNSELECT=\n',out)

    def test_mixed_empty_tokens_preserve_every_nonempty_leaf(self):
        out=self.tcl('set oldraw [list "" Branch1.2 "" MISSING_ELSE3.0 MISSING_DEFAULT4.1]\ndbg_select branch Branch0.0\nputs "OLD=$unselected"')
        self.assertIn('OLD=Branch1.2 MISSING_ELSE3.0 MISSING_DEFAULT4.1',out)

    def test_invalid_nonempty_no_trim_or_wrapper_fallback(self):
        for token in (' ', ' Branch1.2', 'Item1.Branch1.2', '{Branch1.2}', 'Branch1.2\n', '0'):
            with self.subTest(token=token):
                out=self.tcl('set oldraw [list {%s}]\nputs [catch {dbg_select branch Branch0.0} msg]\nputs $msg\nputs "SELECT=$selected"' % token)
                self.assertIn('RVH2 invalid nonempty native selection',out)
                self.assertIn('SELECT=\n',out)

    def test_nonempty_missing_native_leaf_error_not_swallowed(self):
        out=self.tcl('set oldraw [list Branch99.9]\nputs [catch {dbg_select branch Branch0.0} msg]\nputs $msg')
        self.assertIn('1\nnative item not found',out)

    def test_readback_empty_wrong_extra_duplicate_rejected(self):
        for raw in ('{}','[list ""]','[list Branch0.1]', '[list Branch0.0 Branch1.0]', '[list Branch0.0 Branch0.0]'):
            with self.subTest(raw=raw):
                out=self.tcl('set afterraw %s\nputs [catch {dbg_select branch Branch0.0} msg]\nputs $msg' % raw)
                self.assertRegex(out,r'\n1\nRVH2 (exact singleton|duplicate)')

    def test_readback_exact_leaf_with_empty_token(self):
        self.assertIn('PASS',self.tcl('set afterraw [list "" Branch0.0]\ndbg_select branch Branch0.0\nputs PASS'))

    def test_metric_and_expected_identity_rejected(self):
        for metric,meta in (('line','Branch0.0'),('branch','Item0.Branch0.0'),('branch','')):
            out=self.tcl('puts [catch {dbg_select {%s} {%s}} msg]\nputs $msg' % (metric,meta))
            self.assertIn('1\nRVH2',out)

    def test_adapted_namespace_and_pins(self):
        fn=subject.adapted(subject.frozen.pilot.config_read, [("plan['pilot_scopes']", "plan['full_scopes']",1)])
        for key,value in dict(SCRIPT=subject.SCRIPT,TCL=subject.TCL,TEST=subject.TEST,
                              verify_artifacts=subject.verify_artifacts,
                              branch_library=subject.branch_library).items():
            self.assertIs(fn.__globals__[key],value)
        self.assertIs(fn.__globals__['config_read'],fn)
        capture=subject.full_capture()
        self.assertIs(capture.__globals__['config_read'],subject.config_read)
        self.assertIs(capture.__globals__['verify_artifacts'],subject.verify_artifacts)
        pins=subject.pilot_pins()
        self.assertEqual(pins[str(subject.SELECTION)],subject.frozen.sha(subject.SELECTION))
        self.assertEqual(pins[str(subject.frozen.TCL)],subject.frozen.sha(subject.frozen.TCL))

    def test_full_five_stage_host_with_real_selector_empty_scope_fallback(self):
        import test_capture_rvh_branch_pilot_725 as tests
        source=inspect.getsource(tests.PilotTests.test_tcl_five_stage_reset_reload_existing_audit)
        source='\n'.join(line[4:] if line.startswith('    ') else line for line in source.splitlines())+'\n'
        substitutions={
            'subject.branch_library()':'subject.branch_library()',
            'set parts [split $key ,]':'set ::current_scope $scope\n        set ::current {}\n        set ::oldraw [list ""]\n        set parts [split $key ,]',
            'proc dbg_select {metric meta} {set ::current $meta}':STUB,
            '$::current)':'$::current_scope|$::current)',
            "'DBG_AUDIT '+stage+' 100'":"'DBG_AUDIT '+stage+' 1780'",
        }
        for before,after in substitutions.items():
            self.assertIn(before,source);source=source.replace(before,after)
        from types import SimpleNamespace
        proxy=SimpleNamespace(prepared=subject.frozen.prepared,TCL=subject.TCL,
            branch_library=subject.branch_library,debug=subject.frozen.debug,
            ANNOTATION=subject.frozen.ANNOTATION,STAGES=subject.frozen.STAGES)
        full_tests.FullTests.setUpClass()
        self.config=full_tests.FullTests.config
        namespace=dict(subject=proxy,tempfile=tempfile,Path=Path,subprocess=subprocess)
        exec(compile(source,'HOST_FULL247_EMPTY_SELECTION_ONLY','exec'),namespace)
        namespace['test_tcl_five_stage_reset_reload_existing_audit'](self)


if __name__ == '__main__':
    unittest.main()
