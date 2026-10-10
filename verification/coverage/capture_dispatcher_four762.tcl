# Reuse immutable FSM primitives globally; no nested standalone session.
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_native.tcl}]
proc dispatcher_four_session {} {
    global env fx_groups fx_stream
    set env(FSM_PROBE_OUTPUT) $env(DVE_COVERAGE_OUTPUT)
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    set until [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $until} {error "Missing actual executable identity"}
        after 100
    }
    gui_open_cov -hier $::d4_design -testdir [list $::d4_sample] -test [list $::d4_selected] -merge DispatcherFour762Capture
    set tables {}
    foreach id [gui_get_window_ids] {if {[string match CoverageTable.* $id]} {lappend tables $id}}
    if {$tables ne {CoverageTable.1}} {error "Ambiguous coverage table"}
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    fs_save initial.el 1
    fx_audit initial 0
    foreach group $fx_groups {
        fx_context $group
        foreach name [lindex $group 5] {
            fs_select $name
            gui_exclude_items -id CovDetail.1 -list {fsm list} -selected -annotation {Frozen configuration/source-proven FSM point; exact three-group scope}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    fs_save first.el
    fx_audit applied 1
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    fx_audit reset 0
    fs_save reset.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Unresolved native import"}
    fx_audit reloaded 1
    fs_save second.el
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    fx_audit final 0
    fs_save final-empty.el 1
    close $fx_stream
}
if {![info exists ::d4_test_only]} {
    set failed [catch {dispatcher_four_session} message]
    if {$failed} {
        set f [open [file join $env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f "$message\n$::errorInfo"; close $f
        puts "DISPATCHER_FOUR_FAILED $message"
    }
    set cleanup {}
    if {[catch {gui_exclusion -reset; gui_exclusion -id CoverageTable.1 -recalculate; fs_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts DISPATCHER_FOUR_NATIVE_DONE}
    if {[llength $cleanup]} {
        set f [open [file join $env(DVE_COVERAGE_OUTPUT) cleanup-error.txt] w]
        puts $f $cleanup; close $f
    }
    gui_exit -noprompt
}
