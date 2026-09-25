set ::eth_board_library_only 1
source [file normalize [file join [file dirname [info script]] .. ethernet board_probe.tcl]]

set ::program_count 0
set ::status_bits [format %08x 7]
proc open_hw_manager {} {}
proc connect_hw_server {args} {}
proc get_hw_targets {} { return target_0 }
proc open_hw_target {target} {}
proc get_hw_devices {args} { return xcvu9p_0 }
proc get_property {name object} {
    if {$name eq "PART"} { return xcvu9p-flga2104-2L-e }
    if {$name eq "CELL_NAME"} {
        if {$object eq "vio_0"} { return i_vio }
        if {$object eq "axi_0"} { return i_jtag }
    }
    if {$name eq "PROTOCOL"} { return AXI4_Lite }
    if {$name eq "INPUT_VALUE"} { return $::status_bits }
    error "Unexpected property $name on $object"
}
proc current_hw_device {device} {}
proc set_property {name value object} {
    if {$name ni {PROGRAM.FILE PROBES.FILE INPUT_VALUE_RADIX}} { error "Unexpected property write $name" }
}
proc program_hw_devices {device} { incr ::program_count }
proc refresh_hw_device {device} {}
proc get_hw_vios {args} { return vio_0 }
proc get_hw_axis {args} { return axi_0 }
proc refresh_hw_vio {vio} {}
proc get_hw_probes {args} { return probe_in0 }
proc close_hw_target {} {}
proc disconnect_hw_server {} {}
proc close_hw_manager {} {}

set bit [file normalize [info script]]
set ltx $bit
eth_board::run $bit $ltx diagnostic localhost:3121
if {$::program_count != 1} { error "Diagnostic image not programmed exactly once" }
set ::status_bits [format %08x 3]
if {![catch {eth_board::run $bit $ltx diagnostic localhost:3121} error] ||
    ![string match *not\ settled* $error]} {
    error "Bad baseline was accepted: $error"
}
eth_board::run $bit $ltx restore localhost:3121
if {$::program_count != 3} { error "Restore image not programmed" }
puts MOCK_BOARD_PASS
