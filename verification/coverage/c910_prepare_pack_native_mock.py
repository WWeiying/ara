"""Execute actual disk selection + actual entry via eval and GUI-only stubs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import c910_prepare_pack_native as n


def quote(value):
    value=str(value)
    n.need('{' not in value and '}' not in value,'Unsafe Tcl test literal')
    return '{'+value+'}'


STUBS=r'''
set ::current_EL ""
set ::calibration {}
set ::selected ""
proc gui_open_cov {args} {
    if {[lindex $args 1] ne $::pp_design || [lindex $args 3] ne $::pp_vdb || [lindex $args 5] ne $::pp_test} {error "Source/tool bindings not reached"}
    puts MOCK_NATIVE_OPEN_BOUND
}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_action {args} {set ::scope [lindex $args end]; set ::selected ""}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get {args} {
    set names [dict get $::names $::scope]
    set flag [lindex $args 2]
    if {$flag eq "-firstChild"} {if {[llength $args] == 3} {return 1} else {return ""}}
    set item [lindex $args end]
    switch -- $flag {
        -nextSibling {if {$item >= [llength $names]} {return ""} else {return [expr {$item+1}]}}
        -path {return ROW-$item}
        -meta {return META-$item}
        -text {return [lindex $names [expr {$item-1}]]}
        default {error "Unsupported GUI read $args"}
    }
}
proc gui_list_get_selected {args} {
    if {[lindex $args end] eq "-count"} {return [expr {$::selected ne ""}]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lindex $args 2] eq "-unselect"} {set ::selected ""} else {set ::selected [lindex [lindex $args end] 0]}
}
proc gui_exclude_items {args} {
    if {![regexp {^ROW-(\d+)$} $::selected -> index]} {error "Bad native selection"}
    set name [lindex [dict get $::names $::scope] [expr {$index-1}]]
    set line [dict get $::el_rows $::scope $name]
    dict set ::calibration $::scope $name $line
}
proc gui_exclusion {args} {
    if {[lindex $args 0] eq "-reset"} {set ::current_EL "";set ::calibration {}}
}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lindex $args 0] eq "-load"} {
        set f [open $path r];set ::current_EL [read $f];close $f
    } else {
        set text $::current_EL
        dict for {scope rows} $::calibration {
            append text "CHECKSUM: \"[dict get $::checksums $scope]\"\nINSTANCE: $scope\n"
            dict for {name line} $rows {append text "$line\n"}
        }
        set f [open $path w];puts -nonewline $f $text;close $f
    }
}
proc gui_exit {args} {puts MOCK_GUI_EXIT}
'''


def qualify(prepared,c):
    selection=prepared/'selection.tcl'
    n.need(selection.read_bytes()==n.selection(c).encode('ascii') and
           not selection.read_bytes().startswith(b'"') and b'\\n' not in selection.read_bytes(),
           'Actual selection is not real Tcl text')
    bindings=n.source_bindings(c)
    with tempfile.TemporaryDirectory(prefix='c910_prepare_pack_plain_tcl_',dir=n.life.OUT) as directory:
        out=Path(directory)
        (out/'selection.tcl').symlink_to(selection.resolve())
        shutil.copyfile(prepared/'candidate.el',out/'candidate.el')
        mock=dict(c,output=str(out),pins={})
        n.life.save(out/'config.json',mock)
        seal=n.life.digest(out/'config.json')
        setup='set ::env(DVE_COVERAGE_OUTPUT) '+quote(out)+'\n'
        setup+='set ::env(C910_PREPARE_PACK_SEAL) '+quote(seal)+'\n'
        setup+='set ::names {}\nset ::el_rows {}\nset ::checksums {}\n'
        for i in c['instances']:
            setup+='dict set ::names '+quote(i['scope'])+' '+quote(' '.join(i['native_names']))+'\n'
            setup+='dict set ::checksums '+quote(i['scope'])+' '+quote(i['design_checksum']+' '+i['toggle_checksum'])+'\n'
            for node in i['targets']:
                b=bindings[i['scope'],node['name']]
                line='Toggle %s "%s %s[%d:%d]"'%(node['name'],b['native_type'],node['name'],b['left'],b['right'])
                setup+='dict set ::el_rows '+quote(i['scope'])+' '+quote(n.boundary.r.native_name(node))+' '+quote(line)+'\n'
        script=setup+STUBS+'\nset f [open '+quote(n.ENTRY)+' r]\nset body [read $f]\nclose $f\n'
        script+='puts "INFO_SCRIPT [list [info script]]"\neval $body\n'
        result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,cwd=out,timeout=180)
        n.need(result.returncode==0 and not result.stderr and
               'C910_PREPARE_PACK_NATIVE_FAILED' not in result.stdout and
               result.stdout.splitlines().count('C910_PREPARE_PACK_NATIVE_DONE')==1 and
               'INFO_SCRIPT {}' in result.stdout and 'MOCK_NATIVE_OPEN_BOUND' in result.stdout,
               'Actual eval/source/session failed: '+result.stdout+result.stderr)
        stages=[n.check_stage(out,mock,s) for s in n.STAGES]
        n.need((out/'first.el').read_bytes()==(out/'candidate.el').read_bytes()==(out/'second.el').read_bytes(),
               'Complete fixture bytes not reloaded')
        return dict(status='ACTUAL_DISK_TCL_SOURCE_EVAL_FIVE_STAGES_REAL_PYTHON_CHECKS_PASS_NOT_EDA',
            stages=stages,selection_sha256=n.life.digest(selection),stdout=result.stdout,
            calibration=json.loads((out/'calibration-proof.json').read_bytes()),native_qualified=False)
