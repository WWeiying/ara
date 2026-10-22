import pathlib
import subprocess
import tempfile
import unittest

HERE=pathlib.Path(__file__).resolve().parent
MODEL='''
set mode false
set percentages {}
proc p740_summary {stage} {
    if {$::mode ne "false"} {error "Percentage reader sees ratio"}
    lappend ::percentages $stage
}
proc p740_root {} {set ::mode false}
proc p740_select {scope} {return $scope}
proc gui_covtable_setroot {args} {}
proc gui_cov_show_value {args} {set ::mode [lindex $args end]}
proc gui_process_events {args} {}
proc gui_list_get_property {args} {
    set c [lindex $args end]
    if {$c > 10} {error end}
    return [lindex {Score Line Toggle FSM Condition Branch} [expr {$c-5}]]
}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {return 7}
    if {[lsearch -exact $args -nextSibling] >= 0} {return 0}
    if {[lsearch -exact $args -path] >= 0} {return {gen_lane[0]}}
    if {[lindex $args end-1] == 0} {return {gen_lane[0]}}
    if {$::mode ne "true"} {error "Not native ratio mode"}
    return {37 / 58}
}
proc csv_row {stream values} {puts $stream [join $values "|"]}
'''


class Hook(unittest.TestCase):
    def execute(self,body):
        with tempfile.TemporaryDirectory() as tmp:
            script='source {%s}\nset ::env(DVE_COVERAGE_OUTPUT) {%s}\n'%(HERE/'native_toggle_ratio_hook.tcl',tmp)
            result=subprocess.run(['tclsh'],input=script+MODEL+body,text=True,capture_output=True,check=True)
            self.assertEqual(result.stderr,'');self.assertIn('PASS',result.stdout)
            return {p.name:p.read_text() for p in pathlib.Path(tmp).glob('ratios*.csv')}

    def test_actual_namespace_five_stages_percent_first_ratio_restore(self):
        files=self.execute('''
nr_counts::install [list [list {ara_tb.i_ara.gen_lane[0]} {gen_lane[0]}]]
foreach stage {raw applied reset reloaded final} {p740_summary $stage}
if {$mode ne "false" || $percentages ne {raw applied reset reloaded final}} {error sequence}
if {![catch {nr_counts::install [list [list a b]]}]} {error duplicate}
puts PASS
''')
        self.assertEqual(len(files),5)
        for text in files.values():
            self.assertEqual(len(text.splitlines()),7)
            self.assertIn('|7|gen_lane[0]|gen_lane[0]|7|Toggle|37 / 58',text)

    def test_bad_root_rejects_and_restores_without_skipping_percent(self):
        self.execute('''
nr_counts::install [list [list {ara_tb.i_ara.gen_lane[0]} wrong]]
if {![catch {p740_summary raw}]} {error accepted}
if {$mode ne "false" || $percentages ne {raw}} {error cleanup}
puts PASS
''')

    def test_no_auto_install_load_exclude_or_bit_count_inference(self):
        text=(HERE/'native_toggle_ratio_hook.tcl').read_text()
        self.assertNotIn('gui_open_cov',text);self.assertNotIn('gui_exclusion',text)
        self.assertNotIn('{*}',text);self.assertNotIn('dict ',text)


if __name__=='__main__':unittest.main()
