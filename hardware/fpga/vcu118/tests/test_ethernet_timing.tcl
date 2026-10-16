set ::ara_eth_timing_library_only 1
source [file join [file dirname [info script]] .. constraints ethernet_timing.tcl]
proc get_pins {args} { return [lindex $args end] }
proc get_clocks {args} {
    if {[string match */mb/Clk [lindex $args end]]} { return management }
    return ui
}
proc get_property {property object} {
    if {$property ne "PERIOD"} { error "Unexpected property" }
    if {$object eq "management"} { return $::period }
    return 3.333
}
proc get_ports {args} { return [lindex $args end] }
proc all_fanout {args} { return $::endpoints }
proc set_max_delay {args} { lappend ::calls $args }
set period 10.0
set endpoints capture/D
set calls {}
ara_eth_timing::apply
if {[llength $calls] != 4} { error "Expected four bounded pad constraints" }
foreach args $calls {
    if {[lrange $args 0 2] ne {20.0 -datapath_only -from}} { error "Missing source bound" }
}
set period 8.0
if {![catch {ara_eth_timing::apply} error] || ![string match {*clock period*} $error]} {
    error "Wrong clock must fail"
}
set period 10.0
set endpoints {}
if {![catch {ara_eth_timing::apply} error] || ![string match {*capture endpoints*} $error]} {
    error "Missing capture must fail"
}
puts "ETHERNET_TIMING_TEST_PASS"
