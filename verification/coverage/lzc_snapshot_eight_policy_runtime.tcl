# Tcl8.4. Approved seven scope fix is sourced as immutable library only.
set seven_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_seven_policy_runtime_v3.tcl}

proc eight_snapshot_audit {stage active} {
    global env
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) snapshot states_$stage.csv] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream {Stage Scope Expression NativeNames Targets Retained TargetExcluded RetainedExcluded}
    set failed [catch {lzc_batch_audit CoverageTable.1 $stream $stage $active} message]
    close $stream
    qbsapp_root
    if {$failed} {error $message}
    puts "EIGHT_SNAPSHOT_AUDIT $stage 96"
}
proc eight_initialize {} {
    global env eight_before_complete lzc_batch_groups
    seven_initialize
    source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_lzc_batch.tcl}
    source [file join $env(DVE_COVERAGE_OUTPUT) snapshot-selection.tcl]
    set targets 0
    set all 0
    foreach row $lzc_batch_groups {
        incr targets [llength [lindex $row 3]]
        incr all [llength [lindex $row 2]]
    }
    lpd_require [expr {$targets==24 && $all==96 && [llength $lzc_batch_groups]==36}] "Exact24/96/36 required"
    set eight_before_complete 0
    rename qbs_audit eight_prior_audit
    proc qbs_audit {stage active} {
        global eight_before_complete
        eight_prior_audit $stage $active
        eight_snapshot_audit $stage $active
        puts "EIGHT_FULL_AUDIT $stage 23666"
        if {$stage eq "before" && !$active} {set eight_before_complete 1}
    }
    rename seven_load eight_prior_load
    proc seven_load {path} {
        global eight_before_complete
        lpd_require [expr {$eight_before_complete==1}] "Complete23666 before gate closed"
        eight_prior_load $path
    }
    set body [info body qbsapp_session]
    set body [seven_replace_once $body {combined-seven.el} {combined-eight.el}]
    set body [seven_replace_once $body {puts SEVEN_ACTUAL_RELOAD_EXACT5868} {puts EIGHT_ACTUAL_RELOAD_EXACT5892}]
    proc qbsapp_session {} $body
    puts EIGHT_RUNTIME_INSTALLED
}
set failed [catch {eight_initialize; qbsapp_session} message]
if {$failed} {puts "EIGHT_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[llength [info commands eight_prior_audit]]} {
    if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
} else {lappend cleanup {Incomplete eight initialization}}
if {[llength [info commands dbg_save]]} {
    if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
} else {lappend cleanup {Missing native save}}
if {$failed || [llength $cleanup]} {
    puts "EIGHT_FAILED $message cleanup=$cleanup"
} else {
    puts SIX_COMBO_DONE_EXACT5808
    puts EIGHT_DONE_EXACT5892
}
gui_exit -noprompt
