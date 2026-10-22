"""Execute complete pinned Tcl entries and disk selections using GUI-only stubs."""
from pathlib import Path
import subprocess
import tempfile

import fma_expanded_native_03 as native


def quote(value):
    native.require(not any(c in str(value) for c in '{}\\'), 'Unsafe Tcl mock value')
    return '{' + str(value) + '}'


def setup(config, out):
    lines = ['set env(DVE_COVERAGE_OUTPUT) ' + quote(out),
             'set env(FMA_EXPANDED_CONFIG_SEAL) ' + quote(native.life.digest(out / 'config.json')),
             'set expected_helper ' + quote(Path(native.__file__).resolve()),
             'set expected_design ' + quote(str(native.life.IMAGE) + '.vdb')]
    # The exact historical VDB/test are defined by the pinned predecessor selection.
    lines += ['proc read_expected {} {', 'global expected_python expected_scope expected_vdb expected_test',
              'source ' + quote(native.frozen.predecessor.PRODUCT / 'selection.tcl'),
              'set expected_python $fma_python', 'set expected_scope $fma_scope',
              'set expected_vdb $fma_vdb', 'set expected_test $fma_test', '}', 'read_expected']
    el = []
    for i in config['instances']:
        rows = native.frozen.inventory(Path(i['native_identity_source']))
        lines.append('set ' + quote('inventories(' + i['scope'] + ')') + ' [list ' +
                     ' '.join('[list ' + ' '.join(quote(r[k]) for k in ('path', 'meta', 'name')) + ']' for r in rows) + ']')
        el += ['CHECKSUM: "%s %s"' % (i['design_module_checksum'], i['toggle_checksum']),
               'INSTANCE: ' + i['scope']]
        for t in i['targets']:
            lines.append('set ' + quote('expected_targets(' + i['scope'] + ',' + t['native_name'] + ')') + ' 1')
            el.append('Toggle %s "logic %s"' % (t['name'], t['native_name']))
    lines += ['set whole_EL ' + quote('\n'.join(el) + '\n'), 'set saved {}', 'set stages {}',
              'set total_selections 0', 'set selected {}', 'array set excluded {}']
    return '\n'.join(lines) + '\n'


STUBS = r'''
proc gui_open_cov {args} {
    foreach var {fma_scope fma_design fma_vdb fma_test fma_python fma_helper fma_instances fma_seal} {
        if {![info exists ::$var] || [set ::$var] eq ""} {error "Missing global $var"}
    }
    foreach pair {{fma_scope expected_scope} {fma_design expected_design} {fma_vdb expected_vdb}
                  {fma_test expected_test} {fma_python expected_python} {fma_helper expected_helper}} {
        if {[set ::[lindex $pair 0]] ne [set ::[lindex $pair 1]]} {error "Wrong binding $pair"}
    }
    if {![file executable $::fma_python] || ![file isfile $::fma_helper]} {error "Tools unavailable"}
    if {[llength $::fma_instances] != 12 || [array size ::expected_targets] != 612} {error "Wrong scope union"}
    foreach i $::fma_instances {
        if {[llength [lindex $i 1]] != 51 || ![info exists ::inventories([lindex $i 0])]} {error "Wrong scope"}
        foreach name [lindex $i 1] {
            if {![info exists ::expected_targets([lindex $i 0],$name)]} {error "Target drift"}
        }
    }
    if {[lindex $args 1] ne $::expected_design || [lindex $args 3] ne $::expected_vdb ||
        [lindex $args 5] ne $::expected_test} {error "Wrong open args"}
}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_action {args} {
    set ::current_scope [lindex $args end]
    set ::current_rows $::inventories($::current_scope)
}
proc gui_list_get {args} {
    set op [lindex $args 2]
    if {$op eq "-firstChild"} {
        if {[llength $args] == 3} {return 1}
        return ""
    }
    set item [lindex $args end]
    if {$op eq "-nextSibling"} {
        if {$item < [llength $::current_rows]} {return [expr {$item + 1}]}
        return ""
    }
    set row [lindex $::current_rows [expr {$item - 1}]]
    if {$op eq "-path"} {return [lindex $row 0]}
    if {$op eq "-meta"} {return [lindex $row 1]}
    if {$op eq "-text"} {return [lindex $row 2]}
    error "Unexpected gui_list_get $args"
}
proc gui_list_get_selected {args} {
    if {$::selected eq ""} {return {}}
    return [list [list $::selected]]
}
proc gui_list_select {args} {
    if {[lindex $args 2] eq "-unselect"} {set ::selected {}; return}
    if {[lindex $args 2] ne "-select" || [llength [lindex $args 3]] != 1} {error "Not one whole object"}
    set ::selected [lindex [lindex $args 3] 0]
}
proc gui_exclude_items {args} {
    set key "$::current_scope,$::selected"
    if {![info exists ::expected_targets($key)] || [info exists ::excluded($key)]} {error "Non-target/duplicate exclusion"}
    set ::excluded($key) 1
    incr ::total_selections
}
proc gui_exclusion {args} {
    if {[lindex $args 0] eq "-reset"} {array unset ::excluded; array set ::excluded {}}
}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args 2] 0]
    if {[lindex $args 0] eq "-load"} {
        set f [open $path r]; set content [read $f]; close $f
        if {$content ne $::whole_EL} {error "Reload typed EL differs"}
        foreach key [array names ::expected_targets] {set ::excluded($key) 1}
        return
    }
    if {[lindex $args 0] ne "-save"} {error "Unexpected EL action"}
    set content ""
    if {[array size ::excluded]} {
        if {[array size ::excluded] != 612} {error "Partial EL"}
        set content $::whole_EL
    }
    set f [open $path w]; puts -nonewline $f $content; close $f
    lappend ::saved [file tail $path]
}
rename exec actual_exec
proc exec {args} {
    if {[lindex $args 0] ne $::expected_python || [lindex $args 2] ne $::expected_helper ||
        [lindex $args 3] ne "stage" || [lindex $args 5] ne $::env(DVE_COVERAGE_OUTPUT) ||
        [lindex $args 7] ne $::env(FMA_EXPANDED_CONFIG_SEAL)} {error "Wrong stage tool binding"}
    lappend ::stages [lindex $args 9]
    return [eval [linsert $args 0 actual_exec]]
}
proc gui_exit {args} {}
'''


def evaluate(entry, program):
    # Read the complete script then eval at top level, without extracting procs.
    command = program + '\nset entry [open ' + quote(entry) + ' r]\nset code [read $entry]\nclose $entry\neval $code\n'
    command += 'puts [list MOCK_STATE $total_selections $stages $saved INFO_SCRIPT [info script]]\n'
    result = subprocess.run(['tclsh'], input=command, text=True, capture_output=True)
    native.require(result.returncode == 0 and not result.stderr, 'Tcl mock failure: ' + result.stderr)
    return result.stdout


def reproduce_02():
    # Real sealed selection is sourced in place; GUI stubs never write to 02.
    mock = 'set total_selections 0\nset stages {}\nset saved {}\nproc gui_exit {args} {}\n'
    mock += 'proc gui_exclusion {args} {error MOCK_NO_WRITES_TO_SEALED_02}\n'
    mock += 'set env(DVE_COVERAGE_OUTPUT) ' + quote(native.OLD) + '\nset env(FMA_EXPANDED_CONFIG_SEAL) sealed02\n'
    result = evaluate(native.HERE / 'fma_expanded_native_02.tcl', mock)
    native.require('FMA_EXPANDED_NATIVE_CAPTURE_FAILED invalid command name' in result and
                   'FMA_EXPANDED_NATIVE_CAPTURE_DONE' not in result, 'Sealed02 failure not reproduced')
    return result


def qualify_disk_entry(selection):
    native.require(selection.read_bytes() == native.selection_text().encode('ascii') and
                   not selection.read_bytes().startswith(b'"') and b'\\n' not in selection.read_bytes(),
                   'Actual selection is JSON/escaped or differs')
    c = native.life.read_bound(native.OLD / 'config.json', native.OLD_SEAL)
    rejected = reproduce_02()
    with tempfile.TemporaryDirectory(prefix='fma_expanded_plain_tcl_03_') as tmp:
        out = Path(tmp)
        # The symlink sources the actual generated file, not a reconstructed fixture.
        (out / 'selection.tcl').symlink_to(selection.resolve())
        native.life.save(out / 'config.json', dict(c, output=str(out), pins={}))
        result = evaluate(native.ENTRY, setup(c, out) + STUBS)
        native.require('FMA_EXPANDED_NATIVE_CAPTURE_DONE' in result and
                       'FMA_EXPANDED_NATIVE_CAPTURE_FAILED' not in result and
                       'MOCK_STATE 612 {initial apply reset reload final}' in result and
                       'INFO_SCRIPT {}' in result, 'Actual entry/session did not complete: ' + result)
        stages = [native.frozen.check_stage(out, s, c) for s in native.frozen.STAGES]
        return dict(status='ACTUAL_DISK_SOURCE_SESSION_EVAL_GUI_MOCK_PASS_NOT_NATIVE',
                    sealed02_failure_reproduced=rejected, successor_stdout=result,
                    selection_sha256=native.life.digest(selection), stages=stages,
                    all_configuration_and_tool_bindings_reachable=True, mocked_selection_count=612,
                    real_python_stage_checker=True, native_qualification=False)
