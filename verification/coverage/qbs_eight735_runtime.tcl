# Tcl8.4. One disposable session; no persistent/global application.
proc qe_union {path} {
    global env qe_expected
    set got [nem_records [qs_bytes $path]]
    qbf_require [expr {[llength $got]==7684 && $got eq $qe_expected}] "Exact7684 identity/attribute/annotation union differs"
}
proc qe_initialize {} {
    global env qs_output qe_expected qe_mapped qbf_stream
    source [file join $env(DVE_COVERAGE_OUTPUT) csv-row-library.tcl]
    puts EIGHT_CSV_WRITER_INSTALLED
    source [file join $env(DVE_COVERAGE_OUTPUT) eight-library.tcl]
    eight_initialize
    set ::qnm_test_only 1
    uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qbs_full1792_qualification_multiset_v2.tcl}]
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) qbs-side-selection.tcl]]
    set qe_expected [nem_records [qs_bytes [file join $env(DVE_COVERAGE_OUTPUT) combined-nine.el]]]
    qbf_require [expr {[llength $qe_expected]==7684}] "Exact7684 proposal required"
    set qbf_stream [open [file join $qs_output native-qualification.tcllist] w]
    set qe_mapped 0
    rename qbs_audit qe_eight_audit
    proc qbs_audit {stage active} {
        global qe_mapped qbf_scopes qn_meta
        qe_eight_audit $stage $active
        if {!$qe_mapped} {
            qbf_require [expr {$stage eq "before" && !$active}] "Mapping must precede import"
            array set qn_meta {}
            foreach bank $qbf_scopes {qbf_scope [lindex $bank 0] [lindex $bank 1]}
            qbf_require [expr {[array size qn_meta]==1344}] "Incomplete actual1344 native mapping"
            set qe_mapped 1
        }
        qn_audit $stage $active
        qbsapp_root
        puts "QBS_EIGHT_FULL_AUDIT $stage 27250"
    }
    rename dbg_save qe_eight_save
    proc dbg_save {name {empty 0}} {
        global env
        qe_eight_save $name $empty
        if {!$empty} {qe_union [file join $env(DVE_COVERAGE_OUTPUT) $name]}
    }
    set body [info body qbsapp_session]
    set body [seven_replace_once $body {combined-eight.el} {combined-nine.el}]
    set needle {lpd_require [expr {[lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] eq
        [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]}] "Combined EL actual reload bytes differ"}
    set replacement {set qe_count [nem_require_equal [qs_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] [qs_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]]
    qbf_require [expr {$qe_count==7684}] "Exact7684 reload multiset differs"
    puts QBS_EIGHT_RELOAD_MULTISET_EXACT7684}
    set body [seven_replace_once $body $needle $replacement]
    proc qbsapp_session {} $body
    puts QBS_EIGHT_RUNTIME_INSTALLED
}
proc qe_main {} {
    global qbf_stream
    set failed [catch {qe_initialize; qbsapp_session} message]
    if {$failed} {puts "QBS_EIGHT_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[llength [info commands qe_eight_audit]]} {
        if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Incomplete combination initialization}}
    if {[llength [info commands qe_eight_save]]} {
        if {[catch {dbg_save final-empty.el 1; dbg_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Missing global native empty save}}
    if {[info exists qbf_stream]} {
        qn_log [list terminal $failed $message $cleanup]
        close $qbf_stream
    }
    if {$failed || [llength $cleanup]} {puts "QBS_EIGHT_HOLD $message cleanup=$cleanup"} else {
        puts SIX_COMBO_DONE_EXACT5808
        puts EIGHT_DONE_EXACT5892
        puts QBS_EIGHT_COMPLETE7684_NOT_APPLICATION
    }
    gui_exit -noprompt
}
if {![info exists qe_library_only]} {qe_main}
