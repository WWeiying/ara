# Same five-stage session; only its generated protected-name list has six aliases.
set ::cast_test_only 1
set stream [open [file join [file dirname [info script]] capture_cast168_native.tcl] r]
set body [read $stream]
close $stream
uplevel #0 $body
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
