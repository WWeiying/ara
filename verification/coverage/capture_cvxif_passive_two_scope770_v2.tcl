# Narrow successor: actual help supports -count/-first, not -meta.
set cv_external_test [info exists ::cv_test_only]
set ::cv_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_cvxif_passive_two_scope770.tcl}
if {!$cv_external_test} {unset ::cv_test_only}
proc cv_select_detail {path meta} {
    set old [gui_list_get_selected -id CovDetail.1 -flat]
    foreach group $old {
        if {$group eq "" || $group eq "{}"} {continue}
        if {[llength $group] == 1} {set group [lindex $group 0]}
        gui_list_select -id CovDetail.1 -unselect [list $group]
    }
    cv_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Detail selection did not clear"
    gui_list_select -id CovDetail.1 -select [list $path]
    cv_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 1}] "Detail not singleton"
    set actual [gui_list_get_selected -id CovDetail.1 -first]
    if {[llength $actual] == 1} {set actual [lindex $actual 0]}
    cv_need [expr {$actual eq $path || $actual eq $meta}] "Native detail selection identity"
}
if {!$cv_external_test} {
    if {[catch {cv_session} message]} {
        puts "CVXIF_TWO_SCOPE_FAILED $message"
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] {WRONLY CREAT EXCL}]
        puts $f $message; puts $f $::errorInfo; close $f
        if {[catch {cv_reset; cv_save cleanup-empty.el} cleanup]} {puts "CVXIF_CLEANUP_FAILED $cleanup"}
    }
    gui_exit -noprompt
}
