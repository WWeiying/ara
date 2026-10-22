import pathlib
import subprocess
import unittest

HERE=pathlib.Path(__file__).resolve().parent


class Recovery(unittest.TestCase):
    def test_actual_source_root_binding_and_display_cleanup(self):
        script='source {%s}\n' % (HERE/'native_toggle_ratio_recovery.tcl')
        script+='''
set ratio false
proc p740_root {} {set ::ratio false}
proc p740_select {scope} {return $scope}
proc gui_covtable_setroot {args} {}
proc gui_cov_show_value {args} {set ::ratio [lindex $args end]}
proc gui_process_events {args} {}
proc gui_list_get_property {args} {if {[lindex $args end] == 5} {return Toggle}; error end}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {return 1}
    if {[lsearch -exact $args -nextSibling] >= 0} {return 0}
    if {[lsearch -exact $args -path] >= 0} {return i_system}
    if {[lindex $args end-1] == 0} {return i_system}
    if {$::ratio ne "true"} {error "Not ratio mode"}
    return {37 / 58}
}
proc csv_row {stream values} {set ::observed $values}
native_toggle_ratio_row {ara_tb.dut.i_system} i_system unused raw
if {$ratio ne "false" || [lindex $observed end] ne "37 / 58"} {error lost}
if {![catch {native_toggle_ratio_row {ara_tb.dut.i_system} wrong unused raw}]} {error accepted}
if {$ratio ne "false"} {error leaked}
puts PASS
'''
        r=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,check=True)
        self.assertEqual(r.stderr,''); self.assertEqual(r.stdout.strip(),'PASS')

    def test_no_application_or_denominator_inference(self):
        text=(HERE/'native_toggle_ratio_recovery.tcl').read_text()
        self.assertNotIn('gui_open_cov',text)
        self.assertNotIn('gui_exclusion',text)
        self.assertNotIn('{*}',text)
        self.assertNotIn('expr ',text)


if __name__=='__main__':unittest.main()
