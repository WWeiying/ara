# Absolute frozen entry: no info-script context, regex names, or guessed IDs.
set ::qfp_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/queue_fp_temporaries_native.tcl}
if {![info exists ::qfp_alias_test_only]} {
    if {[catch {qfp_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message; puts $stream $::errorInfo; close $stream
        puts "QUEUE_FP_TEMP_NATIVE_FAILED $message"
        catch {qfp_reset; fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
