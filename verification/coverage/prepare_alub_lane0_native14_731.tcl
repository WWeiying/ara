# No standalone launch authority. Parent-reviewed single native capture only.
source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
set failed [catch {dbg_session} message]
if {$failed} {puts "DBG_SESSION_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists dbg_scopes]} {
    if {[catch {dbg_audit final 0} detail]} {lappend cleanup $detail}
}
if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
if {$failed || [llength $cleanup]} {
    puts "DBG_CAPTURE_FAILED $message cleanup=$cleanup"
} else {puts DBG_CAPTURE_DONE}
gui_exit -noprompt
