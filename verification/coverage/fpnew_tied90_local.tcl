# Existing Tcl8.4 inventory/flags primitives; no predecessor session is run.
set mq_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/mfpu272_five_phase.tcl}
unset mq_test_only
proc tied_gate {mode} {
    puts [exec $::tied_python -B $::tied_helper $mode --output $::env(DVE_COVERAGE_OUTPUT) --seal $::tied_seal]
}
proc tied_session {} {
    global env mq_design mq_vdb mq_test mq_instances tied_python tied_helper tied_seal
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $mq_design -testdir [list $mq_vdb] -test [list $mq_test] -merge Tied90LocalOnly
    p740_root
    qc_save initial-empty.el
    qc_need [expr {[file size [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]] == 0}] "Initial exclusions"
    set flags [open [file join $env(DVE_COVERAGE_OUTPUT) flags.tsv] w]
    puts $flags "stage\tscope\tlabel\texcluded"
    mq_audit before $flags
    tied_gate before
    mq_load candidate.el
    mq_audit applied $flags
    qc_save first.el
    tied_gate first
    qc_reset
    mq_audit reset $flags
    qc_save reset-empty.el
    mq_load first.el
    mq_audit reloaded $flags
    qc_save second.el
    tied_gate second
    qc_reset
    mq_audit final $flags
    qc_save final-empty.el
    close $flags
    puts FPNEW_TIED90_FIVE_PHASE_DONE
}
if {![info exists ::tied_test_only]} {
    if {[catch {tied_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "FPNEW_TIED90_FAILED $message"
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "TIED_CLEANUP_FAILED $cleanup"}
    }
    gui_exit -noprompt
}
