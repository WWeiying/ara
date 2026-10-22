# Reuse the proven full inventory and global-empty SOC local session.
set ptw_run_entry [expr {![info exists ::soc_test_only] && ![info exists ::ptw_test_only]}]
set soc_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/soc_constants61_native.tcl}
unset soc_test_only
if {$ptw_run_entry} {
    if {[catch {soc_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "PTW_RVH0_OUTPUTS156_FAILED $message"
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "PTW156_CLEANUP_FAILED $cleanup"}
    } else {
        puts PTW_RVH0_OUTPUTS156_FIVE_PHASE_DONE
    }
    gui_exit -noprompt
}
