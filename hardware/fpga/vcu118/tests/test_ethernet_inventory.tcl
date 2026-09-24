set script [file normalize [file join [file dirname [info script]] .. ethernet inventory.tcl]]
set ::argv {}
set ::calls {}
set ::targets {target0}
set ::devices {xcvu9p_0}
proc open_hw_manager {} { lappend ::calls open_manager }
proc connect_hw_server {args} { lappend ::calls connect }
proc get_hw_targets {} { return $::targets }
proc open_hw_target {target} { lappend ::calls open_target }
proc get_hw_devices {args} { return $::devices }
proc get_property {name object} {
    if {$name ne "PART"} { error "Unexpected property" }
    return xcvu9p-flga2104-2L-e
}
proc close_hw_target {} { lappend ::calls close_target }
proc disconnect_hw_server {} { lappend ::calls disconnect }
proc close_hw_manager {} { lappend ::calls close_manager }

source $script
if {$::calls ne {open_manager connect open_target close_target disconnect close_manager}} {
    error "Unexpected successful inventory calls: $::calls"
}
set ::calls {}
set ::targets {target0 target1}
if {![catch {source $script} err] || ![string match {*exactly one JTAG target*} $err]} {
    error "Multiple-target gate failed: $err"
}
if {$::calls ne {open_manager connect disconnect close_manager}} {
    error "Multiple-target inventory opened a device: $::calls"
}
puts "ETHERNET_INVENTORY_MOCK_PASS"
