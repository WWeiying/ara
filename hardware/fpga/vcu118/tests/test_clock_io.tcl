# Diagnostic plumbing only: this does not model debug-hub implementation.
if {[llength [info commands try]]} { rename try {} }
source [file join [file dirname [info script]] .. scripts common.tcl]
set dir [file normalize [lindex $argv 0]]
file mkdir $dir
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc get_cells {args} {
    if {[lindex $args end] eq "dbg_hub"} { return dbg_hub }
    return input_driver
}
proc list_property {object} { return {REF_NAME IS_BLACKBOX} }
proc get_property {key object} {
    if {$::query_failure} { error "Clock query failed" }
    if {$key eq "IS_BLACKBOX"} { return $::blackbox }
    return [expr {$object eq "dbg_hub" ? "dbg_hub" : "IBUF"}]
}
proc get_ports {args} { return [lindex $args end] }
proc get_pins {args} {
    if {[lsearch -exact $args -leaf] >= 0} { return input_driver/O }
    set pin [lindex $args end]
    if {$pin eq {dbg_hub/sl_iport1_o[1]}} { return {} }
    return [list $pin]
}
proc get_clocks {args} {
    if {$::blackbox && [string match *sl_iport* [lindex $args end]]} { return {} }
    return soc_clk
}
proc get_nets {args} { return clock_net }
foreach blackbox {1 0} {
    set query_failure 0
    write_clock_io_details $dir
    set fd [open $dir/clock_io.rpt]; set report [read $fd]; close $fd
    foreach text [list "IS_BLACKBOX=$blackbox" {OBJECT uart_rx_i} \
        {OBJECT c0_ddr4_reset_n} {DRIVER_CELL=input_driver REF_NAME=IBUF} \
        {MISSING pin dbg_hub/sl_iport1_o[1]}] {
        assert {[string first $text $report] >= 0} "missing diagnostic $text"
    }
    set clock [expr {$blackbox ? "" : "soc_clk"}]
    set row [format {OBJECT dbg_hub/sl_iport0_o[1] CLOCKS=%s} $clock]
    assert {[string first "$row\n" $report] >= 0} "actual clock coverage, never invented"
}
set before [lsort [chan names]]
set query_failure 1
assert {[catch {write_clock_io_details $dir} message]} "propagate query failure"
assert {$message eq "Clock query failed"} "preserve cause"
assert {[lsort [chan names]] eq $before} "close report on failure"
puts "PASS: clock/IO evidence for blackbox, implemented and failed-query cases"
