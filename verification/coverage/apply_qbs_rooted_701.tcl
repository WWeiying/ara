# Exact701 successor. Preserve the frozen GUI primitives and require the known body.
source [file join $env(DVE_COVERAGE_OUTPUT) root-helpers.tcl]
set needle {($qbsapp_count != 1 && $qbsapp_count != 699)}
set body [info body qbsapp_session]
if {[string first $needle $body] < 0 || [string first $needle $body] != [string last $needle $body]} {
    error "Frozen population contract differs"
}
proc qbsapp_session {} [string map [list $needle {$qbsapp_count != 701}] $body]
set failed [catch {qbsapp_session} message]
if {$failed} {puts "QBSAPP_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists dbg_scopes]} {
    if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
}
if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
if {$failed || [llength $cleanup]} {puts "QBSAPP_FAILED $message cleanup=$cleanup"} else {puts QBSAPP_DONE_EXACT448}
gui_exit -noprompt
