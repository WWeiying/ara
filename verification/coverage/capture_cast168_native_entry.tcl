# Explicit frozen absolute dependency: DVE -script does not set Tcl info script.
set ::cast_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_cast168_native.tcl}
if {![info exists ::cast_v2_test_only]} {
    if {[catch {cast_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message
        puts $stream $::errorInfo
        close $stream
        puts "CAST168_NATIVE_FAILED $message"
        catch {cast_reset;fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
