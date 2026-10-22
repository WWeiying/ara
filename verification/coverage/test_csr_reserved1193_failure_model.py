import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_csr_reserved1193 as old
from csr_reserved1193_group_contract import check_groups

HERE=Path(__file__).resolve().parent
FAILED=old.life.OUT/'csr-reserved1193-native-agent-20261007-01'


class ActualFailure(unittest.TestCase):
    def test_actual_1304_wanted_only8_nodes(self):
        c=old.life.read_bound(FAILED/'config.json','bb4624d77946b3edee17fed9dfaf2b2411c69c8169a72843f31ef84345c05f36')
        with (FAILED/'bits-before.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
        wanted={(t['signal'],bit) for t in c['targets'] for bit in t['source_bits']+t['retained_source_bits']}
        got={(r['signal'],int(r['bit'])) for r in rows}
        self.assertEqual((len(wanted),len(got),len(wanted-got)),(1304,8,1296))
        self.assertTrue(got<=wanted)
        self.assertTrue(all(r['0to1']==r['1to0']=='0' for r in rows))
        with self.assertRaisesRegex(ValueError,'complement missing'):old.check_inventory(FAILED,c,'before')
        self.assertFalse((FAILED/'first.el').exists())
        self.assertEqual((FAILED/'initial-empty.el').read_bytes(),b'')
        self.assertEqual((FAILED/'cleanup-empty.el').read_bytes(),b'')

    def test_actual_separate_main_and_detail_widget_contract(self):
        text=(FAILED/'DVEfiles/session.tcl').read_text()
        self.assertIn('Layout_CovDetail_tglListView_names',text)
        self.assertIn('Layout_CovDetail_tglDetailListView_names',text)
        self.assertIn('0->1,1->0,',text)
        self.assertIn('-list {tgl}',text)

    def test_installed_menu_uses_explicit_uncompress_not_toggle(self):
        text=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/auxx/gui/dve/preferencesCovMainMenu.tcl').read_text()
        self.assertIn('gui_eval_and_log_cmd gui_cov_tgl_compress -id $window -opt $opt',text)
        self.assertIn('gui_cov_tgl_expand "uncompress"',text)


class Groups(unittest.TestCase):
    def test_partition_target_and_retained_both_directions(self):
        self.assertEqual(len(check_groups('dcache_q',range(64),range(1,64),
            [('dcache_q[63:1]','1','1'),('dcache_q[0]','0','0')],True)),64)

    def test_cross_boundary_hold_even_before(self):
        for active in (False,True):
            with self.assertRaisesRegex(ValueError,'crosses'):
                check_groups('dcache_q',range(64),range(1,64),[('dcache_q[63:0]','0','0')],active)

    def test_mixed_or_unknown_direction_rejects(self):
        for states in [('1','0'),('x','x'),('0','0')]:
            with self.assertRaises(ValueError):
                check_groups('uxl',range(2),{0},[('uxl[0]',*states),('uxl[1]','0','0')],True)

    def test_missing_duplicate_outside_reversed_foreign_reject(self):
        for rows in [[('uxl[0]','0','0')],[('uxl[1:0]','0','0'),('uxl[0]','0','0')],
                     [('uxl[2:0]','0','0')],[('uxl[0:1]','0','0')],[('other[1:0]','0','0')]]:
            with self.assertRaises(ValueError):check_groups('uxl',range(2),range(2),rows,False)


class HostModel(unittest.TestCase):
    def test_full_entry_explicit_uncompress_preserves_raw_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            (out/'selection.tcl').write_text('set ::csr_scope scope\nset ::fma_design design\nset ::fma_vdb vdb\nset ::fma_test test\n')
            script='set ::csr_probe_test_only 1\nsource {'+str(HERE/'csr_reserved1193_view_probe.tcl')+'}\n'
            script+='set ::env(DVE_COVERAGE_OUTPUT) {'+tmp+'}\n'
            script+='''
set ::selected {};set ::mode compressed;set ::calls 0
proc help {args} {}
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_dump_common_list {args} {puts ACTUAL_LIST_DUMP}
proc gui_list_action {args} {set ::mode compressed}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get_selected {args} {
    if {[lsearch $args -count]>=0} {return [llength $::selected]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lsearch $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
proc gui_cov_tgl_can_compress {args} {
    if {$args ne {-id CovDetail.1 -opt uncompress}} {error "Wrong API"}
    return 1
}
proc gui_cov_tgl_compress {args} {
    if {$args ne {-id CovDetail.1 -opt uncompress}} {error "Wrong API"}
    set ::mode uncompressed;incr ::calls
}
proc gui_cov_tgl_double_click {args} {error "Forbidden toggling"}
proc gui_exclusion_file {args} {error "Read-only probe cannot import/exclude/save"}
proc gui_exclude_items {args} {error "Read-only probe cannot exclude"}
proc gui_list_get {args} {
    set flag [lindex $args 2];set item [lindex $args end]
    if {$flag eq "-firstChild"} {if {[llength $args]==3} {return 1};return 0}
    if {$flag eq "-nextSibling"} {if {$::mode eq "uncompressed" && $item eq "1"} {return 2};return 0}
    if {$::mode eq "uncompressed"} {
        if {$item eq "1"} {return {dcache_q[63:1]}};return {dcache_q[0]}
    }
    return {dcache_q[63:0]}
}
csr_probe
if {$::calls != 2} {error "Missing explicit calls"}
'''
            result=subprocess.run(['tclsh'],input='if {[catch {\n'+script+'\n} message]} {puts stderr $message;puts stderr $::errorInfo;exit 1}\n',text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with (out/'expanded-after-0.tsv').open() as f:rows=list(csv.reader(f,delimiter='\t'))
            self.assertEqual(rows[1:],[['dcache_q[63:1]']*3,['dcache_q[0]']*3])
            self.assertIn('CSR1193_READONLY_PROBE_DONE_NOT_QUALIFICATION',result.stdout)

    def test_realistic_default_object_list_does_not_become_bit_list(self):
        # This is the rejected assumption in old test_full_standalone_five_stage_entry.
        with (FAILED/'objects-before.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
        targets=old.expected_bits()
        singletons=[r for r in rows if r['name'] in targets and r['name'].startswith('mstatus_')]
        self.assertEqual(len(singletons),8)
        self.assertIn('dcache_q[63:0]',{r['name'] for r in rows})
        self.assertNotIn('dcache_q[0]',{r['name'] for r in rows})


if __name__=='__main__':unittest.main()
