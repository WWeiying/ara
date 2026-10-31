set rebuild_test_mode 1
source [file join [file dirname [info script]] .. ethernet rebuild_mainrtl_v2.tcl]
set design_top test_top
set calls {}
foreach name {write_checkpoint report_timing_summary report_timing} {
    proc $name {args} {lappend ::calls [list [lindex [info level 0] 0] {*}$args]}
}
proc report_route_status {args} {
    lappend ::calls [list report_route_status {*}$args]
    if {[lindex $args 0] eq "-file"} {return}
    if {[lindex $args 1] eq "ROUTED_FULLY"} {return $::full}
    return $::errors
}
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Supply new output directory"}
foreach {full errors accepted} {1 0 1 0 0 0 1 1 0 invalid 0 0} {
    set calls {}
    set result [catch {rebuild_route_boundary $root case_${full}_${errors}} message]
    if {$result != !$accepted} {error "Incorrect route acceptance: $message"}
    if {[lindex [lindex $calls 0] 0] ne "write_checkpoint"} {error "Evidence must be saved first"}
    if {[llength $calls] < 6} {error "Missing reports before route decision"}
}
puts "PASS: route boundaries preserve diagnostics and reject incomplete/error/invalid routing"
