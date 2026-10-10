# Preserve the frozen v2 body. Global selection is required by dw_audit.
set stream [open {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742_v2.tcl} r]
set body [read $stream]; close $stream
set boundary [string first {set failed [catch} $body]
if {$boundary < 0} {error "Frozen session boundary changed"}
uplevel #0 [string range $body 0 [expr {$boundary-1}]]
source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]
if {![info exists dw_resume_test_only]} {
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
}
