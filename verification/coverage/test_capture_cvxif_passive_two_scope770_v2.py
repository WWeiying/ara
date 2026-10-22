import subprocess
import unittest
import capture_cvxif_passive_two_scope770_v2 as v2


class Readback(unittest.TestCase):
    def test_actual_entry_readback_and_wrong_token(self):
        script='set ::cv_test_only 1\nsource {'+str(v2.old.HERE/'capture_cvxif_passive_two_scope770_v2.tcl')+'}\n'+'''
set ::selected [list [list {old item}]]
proc gui_list_get_selected {args} {
 if {[lsearch -exact $args -meta] >= 0} {error UNSUPPORTED_META}
 if {[lsearch -exact $args -count] >= 0} {return [llength $::selected]}
 if {[lsearch -exact $args -first] >= 0} {return [lindex $::selected 0]}
 return $::selected
}
proc gui_list_select {args} {
 if {[lsearch -exact $args -unselect] >= 0} {
  if {[lindex [lindex $args end] 0] ne "old item"} {error NORMALIZATION}
  set ::selected {}
 } else {set ::selected [lindex $args end]}
}
cv_select_detail {a.b[0].native row} NativeToken0
if {$::selected ne [list {a.b[0].native row}]} {error QUOTING}
set ::selected {}
proc gui_list_select {args} {set ::selected [list WRONG]}
if {![catch {cv_select_detail expected NativeToken0}]} {error MISSING_REJECTION}
puts NATIVE_READBACK_STUB_PASS
'''
        r=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=10)
        self.assertEqual(r.stderr,''); self.assertIn('NATIVE_READBACK_STUB_PASS',r.stdout)

    def test_original01_bytes_still_bound(self):
        out=v2.old.life.OUT/'cvxif-passive-two-scope-native770-agent-20261007-01'
        c=v2.old.life.read_bound(out/'config.json','ebdd37e198d5e13a8e3e7e2253018e7c4aa758db1a9fd4a0c73366078e9e5541')
        for name in ('capture_cvxif_passive_two_scope770.py','capture_cvxif_passive_two_scope770.tcl'):
            p=v2.old.HERE/name
            self.assertEqual(v2.old.life.digest(p),c['pins'][str(p)])


if __name__=='__main__': unittest.main()
