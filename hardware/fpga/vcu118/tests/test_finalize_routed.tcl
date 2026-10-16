set finalize_test_mode 1
source [file join [file dirname [info script]] .. ethernet finalize_routed.tcl]
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "New directory required"}
file mkdir $root
set input [file join $root original.dcp]
set f [open $input w]; puts $f original; close $f
rename source original_source
proc source {args} {}
proc require_vivado {} {}
proc current_project {args} {return {}}
proc open_checkpoint {path} {lappend ::calls open}
proc close_project {} {lappend ::calls close}
proc check_pulsed_latches {dir {reject true}} {
    lappend ::calls pslt
    if {$reject && $::case eq "pslt"} {error "PSLT remains"}
}
proc route_design {args} {
    if {$args ne "-finalize"} {error "Only finalize allowed"}
    lappend ::calls finalize
    if {$::case eq "finalize_fail"} {error "Finalize failed"}
}
proc write_checkpoint {path} {set f [open $path w]; puts $f new; close $f}
proc report_route_status {args} {
    if {[lindex $args end] eq "ERRORS_IN_ROUTES"} {return 0}
    return [expr {$::case ne "unrouted"}]
}
foreach case {pass finalize_fail pslt unrouted} {
    set calls {}
    set failed [catch {finalize_routed package $input [file join $root $case]} message]
    if {$failed != ($case ne "pass")} {error "$case: $message"}
    if {$calls ne {open pslt finalize close} && $case eq "finalize_fail"} {error "Continued after failure"}
    set f [open $input]; set data [read $f]; close $f
    if {[string trim $data] ne "original"} {error "Modified original"}
    puts "PASS finalize $case"
}
