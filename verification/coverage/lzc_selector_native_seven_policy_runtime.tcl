# Tcl 8.4: fresh same-session six policies plus exactly60 measured cond vectors.
proc seven_lzc_audit {stage active} {
    global env seven_rows seven_target_positions lpa_validated_scope
    set lpa_validated_scope {}
    gui_cov_show_cond_ids -show 0
    set path [file join $env(DVE_COVERAGE_OUTPUT) lzc states_$stage.tsv]
    set stream [open $path w]
    puts $stream "position\tscope\tmetric\tnative_id\texpression\tvector\texcluded"
    set count 0
    set failed [catch {
        foreach row $seven_rows {
            set listname [lpb_row $row]
            set value [gui_exclusion -id CovDetail.1 -list $listname -excluded -selected]
            set position [lindex $row 5]
            set wanted [expr {$active && [lsearch -exact $seven_target_positions $position] >= 0}]
            lpd_require [expr {($value eq "0" || $value eq "1") && $value == $wanted}] "Seventh target/protected state differs"
            puts $stream "$position\t[lindex $row 0]\t[lindex $row 1]\t[lindex $row 2]\t[lindex $row 3]\t[lindex $row 4]\t$value"
            incr count
        }
    } message]
    close $stream
    qbsapp_root
    if {$failed} {error $message}
    lpd_require [expr {$count == 4200}] "Incomplete LZC audit"
    puts "SEVEN_LZC_AUDIT $stage $count"
}
proc seven_load {path} {
    global seven_before_complete
    lpd_require [expr {$seven_before_complete == 1}] "Complete23570 before gate is closed"
    gui_exclusion_file -load -file [list $path]
    gui_exclusion -id CoverageTable.1 -recalculate
    lpd_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Combined native import review not empty"
}
proc seven_replace_once {body needle replacement} {
    lpd_require [expr {[string first $needle $body] >= 0 && [string first $needle $body] == [string last $needle $body]}] "Frozen seven session boundary differs"
    return [string map [list $needle $replacement] $body]
}
proc seven_initialize {} {
    global env seven_rows seven_target_positions seven_before_complete
    source [file join $env(DVE_COVERAGE_OUTPUT) six-library.tcl]
    six_initialize
    source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_audit_visibility.tcl}
    source [file join $env(DVE_COVERAGE_OUTPUT) seven-selection.tcl]
    lpd_require [expr {[llength $seven_rows] == 4200 && [llength $seven_target_positions] == 60 &&
        [llength [lsort -unique $seven_target_positions]] == 60}] "Exact60/4200 required"
    set seven_before_complete 0
    rename qbs_audit seven_six_audit
    proc qbs_audit {stage active} {
        global seven_before_complete
        seven_six_audit $stage $active
        seven_lzc_audit $stage $active
        puts "SEVEN_FULL_AUDIT $stage 23570"
        if {$stage eq "before" && !$active} {set seven_before_complete 1}
    }
    set body [info body qbsapp_session]
    set needle {gui_exclusion_file -load -file [list $qbsapp_native]}
    set replacement {seven_load [file join $env(DVE_COVERAGE_OUTPUT) combined-seven.el]}
    set body [seven_replace_once $body $needle $replacement]
    # Replace only the frozen tail; reset is measured before real same-session reload.
    set needle {qbsapp_summary applied
    qbsapp_root
    qbs_audit reloaded 1
    dbg_save after-root.el
    puts SIX_COMBO_AFTER_ROOT_VERIFIED
    gui_exclusion -reset
    qbsapp_root
    qbs_audit reset 0
    dbg_save reset-empty.el 1
    qbsapp_summary reset}
    set replacement {qbsapp_summary applied
    gui_exclusion -reset
    qbsapp_root
    qbs_audit reset 0
    dbg_save reset-empty.el 1
    qbsapp_summary reset
    seven_load [file join $env(DVE_COVERAGE_OUTPUT) applied.el]
    qbsapp_root
    qbs_audit reloaded 1
    dbg_save reloaded.el
    lpd_require [expr {[lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] eq
        [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]}] "Combined EL actual reload bytes differ"
    qbsapp_root
    qbs_audit after-root 1
    dbg_save after-root.el
    puts SIX_COMBO_AFTER_ROOT_VERIFIED
    puts SEVEN_ACTUAL_RELOAD_EXACT5868
    gui_exclusion -reset
    dbg_save session-final-empty.el 1}
    proc qbsapp_session {} [seven_replace_once $body $needle $replacement]
    puts SEVEN_RUNTIME_INSTALLED
}
if {![info exists seven_library_only]} {
    set failed [catch {seven_initialize; qbsapp_session} message]
    if {$failed} {puts "SEVEN_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[llength [info commands seven_six_audit]]} {
        if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Incomplete seven initialization}}
    if {[llength [info commands dbg_save]]} {
        if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Missing native save helper}}
    if {$failed || [llength $cleanup]} {
        puts "SEVEN_FAILED $message cleanup=$cleanup"
    } else {
        puts SIX_COMBO_DONE_EXACT5808
        puts SEVEN_DONE_EXACT5868
    }
    gui_exit -noprompt
}
