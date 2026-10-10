# Environment-only successor. Original capture and binder stay frozen.
set tied_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fpnew_tied90_local.tcl}
unset tied_test_only
proc tied_gate {mode} {
    set child_path {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/tools/soc-venv/lib/python3.9/site-packages}
    puts [exec /usr/bin/env [list PYTHONPATH=$child_path] $::tied_python -B $::tied_helper $mode --output $::env(DVE_COVERAGE_OUTPUT) --seal $::tied_seal]
}
if {![info exists ::tied_env_test_only]} {
    if {[catch {tied_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "FPNEW_TIED90_FAILED $message"
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "TIED_CLEANUP_FAILED $cleanup"}
    }
    gui_exit -noprompt
}
