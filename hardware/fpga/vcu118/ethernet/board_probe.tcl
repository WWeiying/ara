# Program one verified VCU118 image and inspect its debug cores. Hash checks
# and the explicit programming confirmation are enforced by board_probe.py.
namespace eval eth_board {
    proc one {objects description} {
        if {[llength $objects] != 1} {
            error "Expected exactly one $description, found [llength $objects]: $objects"
        }
        return [lindex $objects 0]
    }

    proc run {args} {
        if {[llength $args] != 4} {
            error "Usage: board_probe.tcl image.bit image.ltx diagnostic|restore hw_server_url"
        }
        lassign $args bit probes mode server
        if {$mode ni {diagnostic restore}} { error "Invalid image mode" }
        foreach path [list $bit $probes] {
            if {![file isfile $path]} { error "Missing image file: $path" }
        }
        set manager_open 0
        set server_connected 0
        set target_open 0
        set status [catch {
            open_hw_manager
            set manager_open 1
            connect_hw_server -url $server
            set server_connected 1
            set target [eth_board::one [get_hw_targets] "JTAG target"]
            open_hw_target $target
            set target_open 1
            set device [eth_board::one [get_hw_devices -of_objects $target -filter {PART =~ xcvu9p*}] "xcvu9p device"]
            puts "TARGET $target DEVICE $device PART=[get_property PART $device]"
            current_hw_device $device
            set_property PROGRAM.FILE $bit $device
            set_property PROBES.FILE $probes $device
            program_hw_devices $device
            refresh_hw_device $device
            puts "PROGRAMMED $mode"
            if {$mode eq "diagnostic"} {
                set vios [get_hw_vios -of_objects $device]
                set vio [eth_board::one $vios "diagnostic VIO"]
                set cell [string map {. /} [get_property CELL_NAME $vio]]
                if {![string match "*/i_vio" "/$cell"]} { error "Unexpected VIO cell: $cell" }
                set axes [get_hw_axis -of_objects $device]
                set management {}
                foreach axi $axes {
                    set axi_cell [string map {. /} [get_property CELL_NAME $axi]]
                    if {[string match "*/i_jtag" "/$axi_cell"]} { lappend management $axi }
                }
                set axi [eth_board::one $management "diagnostic management AXI"]
                if {[get_property PROTOCOL $axi] ne "AXI4_Lite"} { error "Management AXI is not AXI4_Lite" }
                set probe [eth_board::one [get_hw_probes -of_objects $vio probe_in0] "status probe"]
                set_property INPUT_VALUE_RADIX HEX $probe
                refresh_hw_vio $vio
                set raw [get_property INPUT_VALUE $probe]
                if {![regexp -nocase {^(0x)?[0-9a-f]{8}$} $raw]} { error "Unexpected VIO status: $raw" }
                scan $raw %x value
                puts [format "STATUS_HEX 0x%08x" $value]
                puts "STATUS_BITS locked=[expr {($value >> 0) & 1}] phy_reset_released=[expr {($value >> 1) & 1}] settled=[expr {($value >> 2) & 1}] axi_error=[expr {($value >> 3) & 1}] echo_enabled=[expr {($value >> 4) & 1}] pcs=[format 0x%04x [expr {($value >> 8) & 0xffff}]]"
                puts "MANAGEMENT_AXI $axi PROTOCOL=[get_property PROTOCOL $axi]"
                if {($value & 7) != 7 || ($value & 0x18) != 0} {
                    error "Diagnostic reset/clock not settled, AXI error, or echo unexpectedly enabled"
                }
                puts "DIAGNOSTIC_BASELINE_PASS"
            } else {
                puts "RESTORE_PROGRAMMED"
            }
        } message options]
        if {$target_open} { catch {close_hw_target} }
        if {$server_connected} { catch {disconnect_hw_server} }
        if {$manager_open} { catch {close_hw_manager} }
        if {$status} { return -options $options $message }
    }
}

if {![info exists ::eth_board_library_only]} {
    if {[catch {eth_board::run {*}$argv} message options]} {
        puts stderr "ETH_BOARD_ERROR $message"
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
