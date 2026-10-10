# Preserve02 namespace correction. Only native label mapping changes.
set ::rvfi02_test_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_system_rvfi788_v2.tcl}]
rename rvfi_bind rvfi02_bind
proc rvfi_bind {stage} {
    global env rvfi_targets rvfi03_targets
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) native-binding-selection.tcl]]
    dw_need [expr {[llength $rvfi03_targets]==788 && [llength [lsort -unique $rvfi03_targets]]==788}] "Exact native targets missing"
    set rvfi_targets $rvfi03_targets
    # The unchanged binder calls the03 Python full1206 parser BEFORE returning selection rows.
    return [rvfi02_bind $stage]
}
if {![info exists ::rvfi03_test_only]} {
    set failed [catch {rvfi_session} message]
    if {$failed} {puts "SYSTEM_RVFI788_FAILED $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {dw_reset} detail]} {lappend cleanup $detail}
    if {[catch {dw_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts SYSTEM_RVFI788_NATIVE_DONE}
    if {[llength $cleanup]} {puts "SYSTEM_RVFI788_FAILED cleanup=$cleanup"}
    gui_exit -noprompt
}
