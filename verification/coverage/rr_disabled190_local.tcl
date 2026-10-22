# Reuse the frozen full-inventory session, including its pre-apply typed gate.
set rr_test_only [info exists ::tied_test_only]
set tied_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fpnew_tied90_local.tcl}
if {!$rr_test_only} {
    unset tied_test_only
    if {[catch {tied_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "RR_DISABLED190_FAILED $message"
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "RR_DISABLED190_CLEANUP_FAILED $cleanup"}
    } else {
        puts RR_DISABLED190_FIVE_PHASE_DONE
    }
    gui_exit -noprompt
}
