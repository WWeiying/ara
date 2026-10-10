# Frozen full-inventory engine; no per-object GUI selection/exclusion.
set pmp_host_only [info exists ::soc_test_only]
set soc_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/soc_constants61_native.tcl}
unset soc_test_only
if {!$pmp_host_only && ![info exists ::pmp_test_only]} {
    if {[catch {soc_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "PMP_CONSTANTS816_FAILED $message"
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "PMP_CONSTANTS816_CLEANUP_FAILED $cleanup"}
    } else {
        puts PMP_CONSTANTS816_FIVE_PHASE_DONE
    }
    gui_exit -noprompt
}
