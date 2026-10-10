# Reuse the actual native first EL. No repeated GUI point selection.
set dw_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742.tcl}
rename dw_session dw_original_selection_session
proc dw_session {} {
    global env dw_design dw_vdb dw_test dw_stream dw_python dw_helper
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Actual executable gate absent"}
        after 100
    }
    gui_open_cov -hier $dw_design -testdir [list $dw_vdb] -test [list $dw_test] -merge DWCPreciseNativeResume
    set dw_stream [open [file join $env(DVE_COVERAGE_OUTPUT) audit.tsv] w]
    dw_save initial-empty.el 1
    dw_audit before 0
    dw_load candidate.el
    dw_audit selected 1
    dw_save first.el
    puts [exec $dw_python -B $dw_helper el --output $env(DVE_COVERAGE_OUTPUT) --file first.el]
    dw_reset
    dw_audit reset 0
    dw_save reset-empty.el 1
    dw_load first.el
    dw_audit reloaded 1
    dw_save second.el
    puts [exec $dw_python -B $dw_helper el --output $env(DVE_COVERAGE_OUTPUT) --file second.el]
    dw_reset
    dw_audit final 0
    dw_save final-empty.el 1
    close $dw_stream
    puts DWC_POINTS_NATIVE_DONE
}
set failed [catch {dw_session} message]
if {$failed} {
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
    puts $stream "$message\n$::errorInfo"; close $stream
    puts "DWC_POINTS_NATIVE_FAILED $message\n$::errorInfo"
}
if {[catch {dw_reset; dw_save cleanup-empty.el 1} cleanup]} {
    puts "DWC_POINTS_NATIVE_FAILED cleanup=$cleanup"
}
gui_exit -noprompt
