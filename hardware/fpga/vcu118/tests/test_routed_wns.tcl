set ::routed_wns_test_mode true
source [file join [file dirname [info script]] .. ethernet repair_routed_wns.tcl]
rename complete_repair::async_signature complete_repair::original_async_signature
rename complete_repair::clock_signature complete_repair::original_clock_signature
proc complete_repair::async_signature {} {return $::async}
proc complete_repair::clock_signature {} {return $::clocks}
proc route_design {args} {
    if {$args ne {-directive Explore}} {error "WNS pass replaced with TNS-only/other mode"}
    incr ::routes
    if {$::drift eq "async"} {set ::async changed}
    if {$::drift eq "clock"} {set ::clocks changed}
}
proc report_route_status {args} {
    if {[lindex $args end] eq "ROUTED_FULLY"} {return $::full}
    return $::errors
}
foreach {drift full errors fail} {none 1 0 0 async 1 0 1 clock 1 0 1 none 0 0 1 none 1 1 1} {
    set ::async original; set ::clocks original; set ::routes 0
    if {[catch {routed_wns::optimize}] != $fail || $::routes != 1} {error "Wrong WNS repair outcome"}
}
if {![catch {routed_wns::run synth a b c d e}]} {error "Synthesis unexpectedly allowed"}
puts "PASS: WNS-directed command, no TNS-only option, route/clock/synchronizer gates"
