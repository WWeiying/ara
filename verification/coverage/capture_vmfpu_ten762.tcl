# Immutable native FSM context/singleton APIs; no imported standalone session.
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_batch.tcl}]
proc v10_audit {stage active} {
    global fx_groups fx_stream
    set bad {}
    foreach group $fx_groups {
        fx_context $group
        foreach name [lindex $group 4] {
            fs_select $name
            set actual [gui_exclusion -id CovDetail.1 -list {fsm list} -excluded -selected]
            set target [expr {[lsearch -exact [lindex $group 5] $name] >= 0}]
            set want 0
            if {$active && [lindex $group 3] eq "State"} {set want STATE_DISPLAY_OBSERVATION}
            if {$active && $target} {set want NATIVE_EL_AUTHORITY}
            puts $fx_stream [join [list $stage [lindex $group 0] [lindex $group 2] [lindex $group 3] $name $actual $want] "\t"]
            flush $fx_stream
            if {$actual ne "0" && $actual ne "1"} {error "Nonboolean native exclusion query"}
            if {$want eq "0" && $actual ne "0"} {lappend bad [list [lindex $group 0] [lindex $group 3] $name]}
        }
    }
    if {[llength $bad]} {error "Protected/reset point excluded or State expanded: $stage $bad"}
}
proc v10_session {} {
    global env fx_groups fx_stream
    set env(FSM_PROBE_OUTPUT) $env(DVE_COVERAGE_OUTPUT)
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Actual executable gate timed out"}
        after 100
    }
    gui_open_cov -hier $::v10_design -testdir [list $::v10_sample] -test [list $::v10_selected] -merge VMFPUTen762
    set tables {}
    foreach id [gui_get_window_ids] {if {[string match CoverageTable.* $id]} {lappend tables $id}}
    if {$tables ne {CoverageTable.1}} {error "Unexpected coverage table"}
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    fs_save initial.el 1
    v10_audit initial 0
    foreach group $fx_groups {
        fx_context $group
        foreach name [lindex $group 5] {
            fs_select $name
            gui_exclude_items -id CovDetail.1 -list {fsm list} -selected -annotation {Frozen configuration/source-proven FSM point; exact three-group scope}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    fs_save first.el
    v10_audit applied 1
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    v10_audit reset 0
    fs_save reset.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Unresolved native import"}
    v10_audit reloaded 1
    fs_save second.el
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    v10_audit final 0
    fs_save final-empty.el 1
    close $fx_stream
}
if {![info exists ::v10_test_only]} {
    set failed [catch {v10_session} message]
    if {$failed} {
        set f [open [file join $env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f "$message\n$::errorInfo"; close $f
        puts "VMFPU_TEN_FAILED $message"
    }
    set cleanup {}
    if {[catch {gui_exclusion -reset; gui_exclusion -id CoverageTable.1 -recalculate; fs_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {[llength $cleanup]} {
        set f [open [file join $env(DVE_COVERAGE_OUTPUT) cleanup-error.txt] w]
        puts $f $cleanup; close $f
    }
    if {!$failed && ![llength $cleanup]} {puts VMFPU_TEN_NATIVE_DONE}
    gui_exit -noprompt
}
