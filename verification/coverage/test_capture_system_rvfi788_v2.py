"""Execute the actual Tcl entry inside a proc, with the full native GUI boundary mocked."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import capture_system_rvfi788_v2 as successor
from test_capture_system_rvfi788 import NativeRVFI


class StandaloneEntry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        NativeRVFI.setUpClass()
        cls.c=NativeRVFI.c

    def execute(self,tmp,mutation=''):
        out=Path(tmp);(out/'DVEfiles').mkdir()
        c=dict(self.c,pins={str(successor.HOOK):successor.life.digest(successor.HOOK)})
        (out/'config.json').write_text(json.dumps(c))
        values=dict(rvfi_design='frozen-design',rvfi_sample='one-vdb',rvfi_test='one-test',
            rvfi_scope=successor.original.review.SCOPE,rvfi_python=sys.executable,
            rvfi_helper=str(Path(successor.__file__).resolve()))
        selection=''.join('set '+key+' {'+value+'}\n' for key,value in values.items())
        selection+='set rvfi_targets [list '+' '.join('{'+p['native_name']+'}' for p in c['targets'])+']\n'
        (out/'selection.tcl').write_text(selection)
        labels=[p['native_name'] for p in c['targets']]+[p['label'] for p in c['protected']]
        tree='set mock_labels [list '+' '.join('{'+name+'}' for name in labels)+']\n'
        declarations='set mock_directives [list '+' '.join('{Toggle '+p['signal']+' "net '+p['native_name']+'"}' for p in c['targets'])+']\n'
        header='CHECKSUM: "'+c['module_checksum']+' 3385959260"\nINSTANCE: '+successor.original.review.SCOPE+'\nANNOTATION: "'+successor.original.ANNOTATION+'"'
        setup='set env(DVE_COVERAGE_OUTPUT) {'+str(out)+'}\n'+tree+declarations+'set mock_header {'+header+'}\n'
        setup+='set mock_selection {};set mock_active {};set mock_action {};set mock_bad_reload 0;set mock_bad_empty 0\n'
        mock=r'''
proc gui_open_cov {args} {
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] w]
    puts $f "The design 'frozen-design' was loaded successfully.";close $f
    if {$::rvfi_scope eq "" || $::rvfi_python eq "" || $::rvfi_helper eq "" || [llength $::rvfi_targets]!=788} {error "Global selection contract missing"}
}
proc gui_list_get {args} {
    set id [lindex $args 1]
    if {$id eq "CoverageTable.1"} {
        if {[lsearch $args -firstChild]>=0} {return root}
        if {[lsearch $args -path]>=0} {return ara_tb}
        return {}
    }
    if {[lsearch $args -firstChild]>=0} {if {[llength $args]==3} {return 1};return 0}
    set item [lindex $args end]
    if {[lsearch $args -nextSibling]>=0} {if {$item<[llength $::mock_labels]} {return [expr {$item+1}]};return 0}
    if {[lsearch $args -path]>=0} {return path$item}
    return [lindex $::mock_labels [expr {$item-1}]]
}
proc gui_list_get_selected {args} {
    if {[lsearch $args -count]>=0} {return [llength $::mock_selection]}
    if {[lsearch $args -first]>=0} {return [lindex $::mock_selection 0]}
    return $::mock_selection
}
proc gui_list_select {args} {
    if {[lsearch $args -unselect]>=0} {set ::mock_selection {};return}
    set ::mock_selection [lindex $args end]
}
proc mock_label {} {
    set token [lindex $::mock_selection 0]
    if {![regexp {^path([0-9]+)$} $token all index]} {error "Bad singleton token"}
    return [lindex $::mock_labels [expr {$index-1}]]
}
proc gui_exclusion {args} {
    if {[lsearch $args -reset]>=0} {set ::mock_active {};return}
    if {[lsearch $args -excluded]>=0} {return [expr {[lsearch -exact $::mock_active [mock_label]]>=0}]}
}
proc gui_exclude_items {args} {
    set name [mock_label]
    if {[lsearch -exact $::rvfi_targets $name]<0} {error "Protected object selected"}
    if {[lsearch -exact $::mock_active $name]>=0} {error "Duplicate exclusion"}
    lappend ::mock_active $name
}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch $args -save]>=0} {
        set f [open $path w]
        if {[llength $::mock_active]} {
            puts $f $::mock_header
            foreach name $::mock_active {puts $f [lindex $::mock_directives [lsearch -exact $::rvfi_targets $name]]}
        } elseif {$::mock_bad_empty} {puts $f extra}
        close $f;return
    }
    set ::mock_active $::rvfi_targets
    if {$::mock_bad_reload} {set ::mock_active [lrange $::mock_active 0 end-1]}
}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_action {args} {
    if {[lindex $args end] ne $::rvfi_scope} {error "Wrong/missing global scope"}
    set ::mock_action $::rvfi_scope
}
foreach cmd {gui_covtable_show gui_covtable_setroot gui_list_expand gui_cov_show_value gui_process_events} {proc $cmd {args} {}}
proc gui_exit {args} {
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) exit-marker] w];puts $f EXIT;close $f
}
'''
        body=setup+mock+mutation+'\nproc boot {} {source {'+str(successor.HOOK)+'}}\nboot\n'
        body+='set f [open [file join $env(DVE_COVERAGE_OUTPUT) csv-probe.csv] w]\ncsv_row $f [list {a,b} {x"y} plain]\nclose $f\n'
        p=subprocess.run(['tclsh'],input='if {[catch {\n'+body+'\n} why]} {puts stderr "$why\n$::errorInfo";exit 1}\n',
            text=True,capture_output=True,timeout=120)
        return p,out

    def test_complete_standalone_nested_entry_five_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,out=self.execute(tmp)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn('SYSTEM_RVFI788_NATIVE_DONE',p.stdout)
            self.assertNotIn('SYSTEM_RVFI788_FAILED',p.stdout)
            for stage in ('before','selected','reset','reloaded','final'):
                self.assertEqual(len(successor.original.inventory(out,self.c,stage)),1206)
            self.assertEqual(successor.original.records((out/'first.el').read_text(),self.c),
                successor.original.records((out/'second.el').read_text(),self.c))
            for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
                self.assertEqual((out/name).read_bytes(),b'')
            with (out/'csv-probe.csv').open() as f:self.assertEqual(next(csv.reader(f)),['a,b','x"y','plain'])

    def test_standalone_selection_namespace_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutation='rename gui_open_cov mock_open_cov\nproc gui_open_cov {args} {unset ::rvfi_scope;eval mock_open_cov $args}'
            p,out=self.execute(tmp,mutation)
            self.assertNotIn('SYSTEM_RVFI788_NATIVE_DONE',p.stdout)
            self.assertIn('SYSTEM_RVFI788_FAILED',p.stdout)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_standalone_reload_missing_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,out=self.execute(tmp,'set mock_bad_reload 1')
            self.assertIn('Target exclusion state differs',p.stdout)
            self.assertNotIn('SYSTEM_RVFI788_NATIVE_DONE',p.stdout)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_standalone_nonempty_initial_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,out=self.execute(tmp,'set mock_bad_empty 1')
            self.assertIn('Nonempty global exclusions',p.stdout)
            self.assertNotIn('SYSTEM_RVFI788_NATIVE_DONE',p.stdout)


if __name__=='__main__':unittest.main()
