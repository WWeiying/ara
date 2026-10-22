# Preserve the original capture engine; only its sealed Python helper changes.
set ::zero3_v2_test_only [info exists ::re_test_only]
set ::re_test_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/masku_zero3_native796.tcl}]
if {!$::zero3_v2_test_only} {
    unset ::re_test_only
    set failed [catch {re_session} message]
    if {$failed} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream "$message\n$::errorInfo"; close $stream
        puts "MASKU_ZERO3_FAILED $message\n$::errorInfo"
    }
    set cleanup {}
    if {[catch {dw_reset} detail]} {lappend cleanup $detail}
    if {[catch {dw_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts MASKU_ZERO3_NATIVE_DONE}
    if {[llength $cleanup]} {puts "MASKU_ZERO3_FAILED cleanup=$cleanup"}
    gui_exit -noprompt
}
