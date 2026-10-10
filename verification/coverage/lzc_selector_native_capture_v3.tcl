# Native top-level inventory is distinct from XML monitored subexpressions.
set lsn_v2_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_capture_v2.tcl}
rename lsn_audit lsn_audit_observed_rows
proc lsn_audit {stage target} {
    global lsn_scope lsn_rows
    gui_list_action -id CoverageTable.1 -column Condition $lsn_scope
    set raw [gui_list_get_selected -id CovDetail.1 -list cond -all -flat]
    set actual {}
    foreach value $raw {
        for {set depth 0} {$depth < 4 && [llength $value] == 1} {incr depth} {
            set next [lindex $value 0]
            if {$next eq $value} {break}
            set value $next
        }
        lappend actual $value
    }
    set expected {}
    foreach row $lsn_rows {
        if {[lindex $row 0] eq "cond" && [lsearch -exact $expected [lindex $row 3]] < 0} {
            lappend expected [lindex $row 3]
        }
    }
    lsn_require [expr {[lsort $actual] eq [lsort $expected]}] "Complete native condition expression inventory differs"
    lsn_audit_observed_rows $stage $target
}
set failed [catch {lsn_session} message]
if {$failed} {puts "LSN_V3_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists lsn_rows]} {
    if {[catch {lsn_audit final -1} detail]} {lappend cleanup $detail}
    if {[catch {lsn_save final-empty.el 1} detail]} {lappend cleanup $detail}
}
if {$failed || [llength $cleanup]} {
    puts "LZC_SELECTOR_NATIVE_FAILED $message cleanup=$cleanup"
} else {puts LZC_SELECTOR_NATIVE_CAPTURE_COMPLETE_PENDING_SEMANTIC_REVIEW}
gui_exit -noprompt
