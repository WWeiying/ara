set ::eth_board_library_only 1
source [file normalize [file join [file dirname [info script]] .. ethernet board_probe.tcl]]

set ::program_count 0
set ::status_bits 08000
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
    if {$name eq "NAME"} { return $object }
    if {$name eq "TYPE"} {
        return [expr {$object in {echo_enable phy_request} ? "vio_output" : "vio_input"}]
    }
    if {$name eq "INPUT_VALUE"} {
        if {$object eq "status_sync"} { return $::status_bits }
        if {$object in {locked phy_rst_n_OBUF}} { return 1 }
        if {$object eq "phy_settled"} { return $::settled }
        if {$object eq "response_error"} { return 0 }
    }
    if {$name eq "OUTPUT_VALUE"} { return 0 }
    error "Unexpected property $name on $object"
}
proc current_hw_device {device} {}
proc set_property {name value object} {
    if {$name ni {PROGRAM.FILE PROBES.FILE INPUT_VALUE_RADIX OUTPUT_VALUE_RADIX}} { error "Unexpected property write $name" }
}
proc program_hw_devices {device} { incr ::program_count }
proc refresh_hw_device {device} {}
proc get_hw_vios {args} { return vio_0 }
proc get_hw_axis {args} { return axi_0 }
proc refresh_hw_vio {args} {}
proc get_hw_probes {args} {
    return {locked phy_rst_n_OBUF phy_settled response_error status_sync echo_enable phy_request}
}
proc close_hw_target {} {}
proc disconnect_hw_server {} {}
proc close_hw_manager {} {}

set bit [file normalize [info script]]
set ltx $bit
set ::settled 1
eth_board::run $bit $ltx diagnostic localhost:3121
if {$::program_count != 1} { error "Diagnostic image not programmed exactly once" }
eth_board::run $bit $ltx check localhost:3121
if {$::program_count != 1} { error "Check-only mode programmed the board" }
set ::mdio_count 0
proc eth_board::identify_phy {axi} { incr ::mdio_count }
eth_board::run $bit $ltx mdio localhost:3121
if {$::program_count != 1 || $::mdio_count != 1} {
    error "MDIO-only mode reprogrammed or skipped its probe"
}
set ::settled 0
if {![catch {eth_board::run $bit $ltx check localhost:3121} error] ||
    ![string match *not\ settled* $error]} {
    error "Bad baseline was accepted: $error"
}
eth_board::run $bit $ltx restore localhost:3121
if {$::program_count != 2} { error "Restore image not programmed" }
puts MOCK_BOARD_PASS
