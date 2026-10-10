# Load the frozen 01 primitives without running its entry. Keep all parameters global.
set ::rvfi_test_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_system_rvfi788.tcl}]
set rvfi02_body [info body rvfi_session]
set rvfi02_source {source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]}
if {[string first $rvfi02_source $rvfi02_body] < 0 || [string first $rvfi02_source $rvfi02_body] != [string last $rvfi02_source $rvfi02_body]} {
    error "Frozen selection entry boundary differs"
}
set rvfi02_body [string map [list $rvfi02_source {uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]}] $rvfi02_body]
proc rvfi_session {} "global env rvfi_design rvfi_sample rvfi_test rvfi_scope rvfi_targets rvfi_python rvfi_helper\n$rvfi02_body"
unset rvfi02_body rvfi02_source
# Same CSV primitive as the frozen exporter; available to every rooted helper.
proc csv_row {stream values} {
    set quoted {}
    foreach value $values {
        lappend quoted "\"[string map [list \" \"\"] $value]\""
    }
    puts $stream [join $quoted ,]
}
if {![info exists ::rvfi02_test_only]} {
    set failed [catch {rvfi_session} message]
    if {$failed} {puts "SYSTEM_RVFI788_FAILED $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {dw_reset} detail]} {lappend cleanup $detail}
    if {[catch {dw_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts SYSTEM_RVFI788_NATIVE_DONE}
    if {[llength $cleanup]} {puts "SYSTEM_RVFI788_FAILED cleanup=$cleanup"}
    gui_exit -noprompt
}
