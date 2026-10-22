# Temporary one-point native smoke, not full protection or waiver qualification.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_batch_v5_library.tcl}
set lpq_ready 0
set lpq_injected 0
proc lpq_guard_exclude {args} {
    global lpq_ready lpn_global_before_complete
    lpd_require [expr {$lpq_ready && !$lpn_global_before_complete}] "Smoke requires fresh84 audit and closed full qualification gate"
    lpd_require [expr {[llength $args] == 7 && [lindex $args 0] eq "-id" && [lindex $args 1] eq "CovDetail.1" &&
        [lindex $args 2] eq "-list" && [lindex $args 3] eq "vector" && [lindex $args 4] eq "-selected" &&
        [lindex $args 5] eq "-annotation" && [lindex $args 6] eq {Native singleton smoke only; {spaces braces} [set ::lpq_injected 1] $not_a_variable}}] "Smoke call differs from sealed target"
    set lpq_ready 0
    return [eval [linsert $args 0 gui_exclude_items]]
}
proc lpq_session {} {
    global env lpd_design lpd_testdirs lpd_tests lpb_rows lpb_targets lpb_output lpa_binding lpa_expected
    global lpq_scope lpq_output lpq_local lpq_ready lpq_injected lpn_global_before_complete
    set lpn_global_before_complete 0
    set lpq_ready 0
    set failed [catch {lpq_guard_exclude} message]
    lpd_require [expr {$failed == 1 && $message eq "Smoke requires fresh84 audit and closed full qualification gate"}] "Smoke guard parser/preflight failed before design load"
    puts LZC_NATIVE_SMOKE_GUARD_PREFLIGHT_COMPLETE_GATE_CLOSED_NO_NATIVE_CALL
    lpn_preload
    source $env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION)
    source $env(LZC_SELECTOR_NATIVE_BATCH_SELECTION)
    source $env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS)
    source $env(LZC_SELECTOR_NATIVE_PROBE_SELECTION)
    lpd_require [expr {[llength $lpd_tests] == 707 && [llength $lpb_rows] == 4200 && [llength $lpb_targets] == 120 &&
        [array size lpa_binding] == 1200 && [array size lpa_expected] == 36}] "Exact sealed707 context required"
    set target [lindex $lpb_targets 0]
    lpd_require [expr {[lindex $target 0] == 0 && [lindex $target 2] eq $lpq_scope && [lindex $target 3] eq "cond"}] "Exact first condition candidate required"
    set active [lindex $target 7]
    set row [lindex $lpb_rows $active]
    lpd_require [expr {$active >= 0 && [lindex $row 0] eq $lpq_scope && [lindex $row 1] eq "cond" &&
        [lindex $row 3] eq [lindex $target 4] && [lindex $row 4] eq "1" && [lindex $row 5] == $active}] "Exact source/expression/true-vector binding required"
    set lpq_local {}
    foreach item $lpb_rows {if {[lindex $item 0] eq $lpq_scope} {lappend lpq_local $item}}
    lpd_require [expr {[llength $lpq_local] == 84}] "Exact child84 positions required"
    gui_open_cov -hier $lpd_design -testdir $lpd_testdirs -test $lpd_tests -merge LZC707GuardNativeShortSmokeNotQualification
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_cov_show_cond_ids -show 0
    lpb_save [file join $lpq_output initial-empty.el] 1
    lpb_audit [file join $lpq_output before.tsv] $lpq_local -1
    set listname [lpb_row $row]
    lpd_require [expr {$listname eq "vector"}] "Wrong smoke native metric"
    set lpq_ready 1
    lpq_guard_exclude -id CovDetail.1 -list $listname -selected -annotation {Native singleton smoke only; {spaces braces} [set ::lpq_injected 1] $not_a_variable}
    lpd_require [expr {$lpq_injected == 0}] "Annotation executed as code"
    gui_exclusion -id CoverageTable.1 -recalculate
    lpb_audit [file join $lpq_output selected.tsv] $lpq_local $active
    set first [file join $lpq_output first.el]
    lpb_save $first 0
    lpb_signature $first $target {}
    gui_exclusion -reset
    lpb_audit [file join $lpq_output reset.tsv] $lpq_local -1
    lpb_save [file join $lpq_output reset-empty.el] 1
    gui_exclusion_file -load -file [list $first]
    gui_exclusion -id CoverageTable.1 -recalculate
    lpb_audit [file join $lpq_output reloaded.tsv] $lpq_local $active
    set second [file join $lpq_output second.el]
    lpb_save $second 0
    lpb_signature $second $target {}
    lpd_require [expr {[lpb_bytes $first] eq [lpb_bytes $second]}] "Native smoke save/reload bytes differ"
    lpd_require [expr {!$lpn_global_before_complete && !$lpq_ready}] "Smoke opened full gate or retained application permit"
    puts LZC_NATIVE_GUARD_SMOKE_SESSION_COMPLETE
}
if {![info exists lpq_test_only]} {
    set failed [catch {lpq_session} message]
    set lpq_ready 0
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists lpq_local]} {
        if {[catch {lpb_audit [file join $lpq_output final.tsv] $lpq_local -1} detail]} {lappend cleanup $detail}
        if {[catch {lpb_save [file join $lpq_output final-empty.el] 1} detail]} {lappend cleanup $detail}
    }
    if {$failed || [llength $cleanup]} {puts "LZC_NATIVE_GUARD_SMOKE_FAILED $message cleanup=$cleanup\n$::errorInfo"} else {
        puts LZC_NATIVE_GUARD_SMOKE_COMPLETE_PENDING_OFFLINE_VERIFICATION_NOT_QUALIFICATION
    }
    gui_exit -noprompt
}
