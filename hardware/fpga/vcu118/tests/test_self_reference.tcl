set ::self_reference_test_mode true
source [file join [file dirname [info script]] .. ethernet repair_self_reference.tcl]
set good {
| Reuse mode | High |
| Incremental Directive | TimingClosure |
| Cells | 100.00 | 100.00 | 0.06 | 1000 |
| Nets | 100.00 | 100.00 | 0.00 | 900 |
}
self_reference::require_high_reuse $good
foreach report [list {} [string map {High Low} $good] \
    [string map {TimingClosure RuntimeOptimized} $good] \
    [string map {{100.00 | 100.00} {100.00 | 29.83}} $good] \
    [string map {{100.00 | 100.00} {98.99 | 100.00}} $good] \
    [string map {{100.00 | 100.00} {100.00 | 27.41}} $good] \
    [string map {100.00 101.00} $good] [string map {Nets Pins} $good]] {
    if {![catch {self_reference::require_high_reuse $report}]} {error "Invalid reuse accepted"}
}
if {![catch {self_reference::run synth a b c d e}]} {error "Synthesis unexpectedly allowed"}
rename complete_repair::async_signature complete_repair::original_async_signature
rename complete_repair::clock_signature complete_repair::original_clock_signature
proc complete_repair::async_signature {} {return $::async}
proc complete_repair::clock_signature {} {return $::clocks}
proc read_checkpoint {args} {
    if {$args ne {-incremental -directive TimingClosure current.dcp}} {error "Wrong reference"}
    lappend ::calls reference
}
proc report_incremental_reuse {args} {
    set f [open [lindex $args 1] w]; puts $f $::report; close $f
}
proc route_design {args} {
    if {$args ne {-directive Explore -tns_cleanup}} {error "Wrong routing mode"}
    lappend ::calls route
    if {$::drift eq "async"} {set ::async changed}
    if {$::drift eq "clock"} {set ::clocks changed}
}
proc report_route_status {args} {return [expr {[lindex $args end] eq "ROUTED_FULLY"}]}
set temp [file join [pwd] self_reference_test_[pid]]
file mkdir $temp
set code [catch {
    set ::async original; set ::clocks original; set ::drift none
    set ::report $good; set ::calls {}
    self_reference::optimize current.dcp $temp
    if {$::calls ne {reference route}} {error "Incorrect flow"}
    set ::report [string map {High Low} $good]; set ::calls {}
    if {![catch {self_reference::optimize current.dcp $temp}] || $::calls ne {reference}} {
        error "Low reuse reached routing"
    }
    foreach drift {async clock} {
        set ::async original; set ::clocks original; set ::report $good
        if {![catch {self_reference::optimize current.dcp $temp}]} {error "Drift accepted"}
    }
} message options]
file delete -force $temp
if {$code} {return -options $options $message}
puts "PASS: self-reference high-reuse gate, routing scope and invariant checks"
