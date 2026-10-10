from pathlib import Path
import subprocess
import tempfile
import unittest
import probe_cvxif_detail_selection770 as p


class Probe(unittest.TestCase):
    def test_original02_still_bound(self):
        c=p.life.read_bound(p.FAILED/'config.json',p.SEAL)
        for name in ('capture_cvxif_passive_two_scope770.py','capture_cvxif_passive_two_scope770_v2.py',
                     'capture_cvxif_passive_two_scope770.tcl','capture_cvxif_passive_two_scope770_v2.tcl'):
            path=p.HERE/name
            self.assertEqual(p.life.digest(path),c['pins'][str(path)])

    def test_decode_exact_literal(self):
        value='{{Line 1 [0]}}; $var {braces}\nnext'
        text='key\tcode\tutf8hex\nfirst\t0\t'+value.encode().hex()+'\n'
        self.assertEqual(p.decode(text)['first']['value'],value)

    def test_decode_reject(self):
        for text in ('bad\n','key\tcode\tutf8hex\na\t2\t61\n',
                     'key\tcode\tutf8hex\na\t0\t61\na\t0\t61\n','key\tcode\tutf8hex\na\t0\txx\n'):
            with self.assertRaises(Exception):p.decode(text)

    def test_no_launch_authority(self):
        with self.assertRaises(Exception):p.run(Path('/unused'),'unused',False)

    def test_actual_entry_nested_first_and_handle_model(self):
        # Model deliberately returns a doubly wrapped NAME, neither path nor meta.
        # It must be captured verbatim, not accepted as a native identity.
        with tempfile.TemporaryDirectory(dir=p.life.OUT) as directory:
            out=Path(directory)
            selection=''.join('set ::cp_'+key+' {'+str(value)+'}\n' for key,value in dict(
                design='dummy',vdb='dummy',test='dummy',scope=p.old.SCOPES[0],
                library=p.HERE/'apply_points740_v4.tcl').items())
            (out/'selection.tcl').write_text(selection)
            script='set ::cp_test_only 1\nset ::env(DVE_COVERAGE_OUTPUT) {'+str(out)+'}\nsource {'+str(p.HERE/'probe_cvxif_detail_selection770.tcl')+'}\n'+'''
array set selected {CoverageTable.1 {} CovDetail.1 {}}
proc help {args} {}
proc gui_open_cov {args} {}
proc gui_covtable_show {args} {}
proc gui_covtable_setroot {args} {}
proc gui_list_expand {args} {}
proc gui_cov_show_value {args} {}
proc gui_process_events {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Line}
proc gui_list_get_selected {args} {
 set id [lindex $args 1]
 if {[lsearch -exact $args -count] >= 0} {return [llength $::selected($id)]}
 if {$id eq "CoverageTable.1"} {return [list $::selected($id)]}
 if {[lsearch -exact $args -first] >= 0 && [lsearch -exact $args -flat] < 0} {return [list [list {Display [1]}]]}
 return [list {Display [1]}]
}
proc gui_list_select {args} {
 set id [lindex $args 1]
 if {[lsearch -exact $args -unselect] >= 0} {set ::selected($id) {}} else {set ::selected($id) [lindex $args end]}
}
proc gui_list_get {args} {
 set id [lindex $args 1]
 if {[lsearch -exact $args -firstChild] >= 0} {
  if {$id eq "CoverageTable.1"} {return RootHandle} else {return Item1}
 }
 set token [lindex $args end]
 if {$id eq "CoverageTable.1" && $token eq "RootHandle"} {return ara_tb}
 if {$token ne "Item1" && $token ne "Line1.0" && $token ne "BlockToken1"} {error "UNKNOWN_TOKEN $token"}
 if {[lsearch -exact $args -path] >= 0} {return Line1.0}
 if {[lsearch -exact $args -meta] >= 0} {return BlockToken1}
 return {Display [1]}
}
proc gui_exclusion_file {args} {set f [open [lindex [lindex $args end] 0] w]; close $f}
proc gui_exclude_items {args} {error NO_EXCLUSIONS_ALLOWED}
proc gui_exclusion {args} {error NO_EXCLUSIONS_ALLOWED}
cp_main
'''
            r=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=10)
            self.assertEqual(r.stderr,'');self.assertIn('CVXIF_ONE_ROW_READONLY_DONE',r.stdout)
            data=p.decode((out/'row-api.tsv').read_text())
            self.assertEqual(data['original_handle']['value'],'Item1')
            self.assertEqual(data['original_path']['value'],'Line1.0')
            self.assertEqual(data['original_meta']['value'],'BlockToken1')
            self.assertEqual(data['first_lindex2']['value'],'Display [1]')
            self.assertEqual(data['candidate_0_path']['code'],0)
            self.assertEqual(data['candidate_3_path']['code'],1)
            self.assertEqual((out/'before-empty.el').read_bytes(),b'')
            self.assertEqual((out/'after-empty.el').read_bytes(),b'')


if __name__=='__main__':unittest.main()
