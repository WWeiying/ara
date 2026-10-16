source [file join [file dirname [info script]] .. scripts common.tcl]
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "New directory required"}
proc get_drc_checks {args} {return [expr {$::case eq "unavailable" ? "" : "PSLT-1"}]}
proc report_drc {args} {
    if {$::case eq "report_error"} {error "DRC failure"}
    set f [open [lindex $args end] w]; puts $f evidence; close $f
}
proc get_drc_violations {args} {return [expr {$::case eq "violations" ? "PSLT-1#1" : ""}]}
foreach case {pass unavailable report_error violations} {
    set failed [catch {check_pulsed_latches [file join $root $case]} message]
    if {$failed != ($case ne "pass")} {error "$case: $message"}
    puts "PASS PSLT $case"
}
set case violations
if {[check_pulsed_latches [file join $root before] false] != 1} {error "Lost pre-finalize evidence"}
