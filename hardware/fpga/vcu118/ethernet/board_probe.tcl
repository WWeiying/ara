# Program one verified VCU118 image and inspect its debug cores. Hash checks
# and the explicit programming confirmation are enforced by board_probe.py.
namespace eval eth_board {
    proc one {objects description} {
        if {[llength $objects] != 1} {
            error "Expected exactly one $description, found [llength $objects]: $objects"
        }
        return [lindex $objects 0]
    }

    proc probe_value {vio name type property width} {
        set matches {}
        foreach probe [get_hw_probes -of_objects $vio] {
            if {[get_property NAME $probe] eq $name && [get_property TYPE $probe] eq $type} {
                lappend matches $probe
            }
        }
        set probe [eth_board::one $matches "$name $type probe"]
        set radix [expr {$property eq "INPUT_VALUE" ? "INPUT_VALUE_RADIX" : "OUTPUT_VALUE_RADIX"}]
        set_property $radix HEX $probe
        set raw [get_property $property $probe]
        regsub -nocase {^0x} $raw {} digits
        if {![regexp -nocase {^[0-9a-f]+$} $digits] || [string length $digits] != $width} {
            error "Unexpected $name value: $raw"
        }
        scan $digits %x value
        return $value
    }

    proc run {args} {
        if {[llength $args] != 4} {
            error "Usage: board_probe.tcl image.bit image.ltx diagnostic|check|restore hw_server_url"
        }
        lassign $args bit probes mode server
        if {$mode ni {diagnostic check restore}} { error "Invalid image mode" }
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
            if {$mode ne "check"} { set_property PROGRAM.FILE $bit $device }
            set_property PROBES.FILE $probes $device
            if {$mode ne "check"} { program_hw_devices $device }
            refresh_hw_device $device
            if {$mode eq "check"} { puts "CHECK_ONLY no programming attempted" } else { puts "PROGRAMMED $mode" }
            if {$mode in {diagnostic check}} {
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
                refresh_hw_vio -update_output_values $vio
                set locked [eth_board::probe_value $vio locked vio_input INPUT_VALUE 1]
                set phy_reset [eth_board::probe_value $vio phy_rst_n_OBUF vio_input INPUT_VALUE 1]
                set settled [eth_board::probe_value $vio phy_settled vio_input INPUT_VALUE 1]
                set axi_error [eth_board::probe_value $vio response_error vio_input INPUT_VALUE 1]
                set sync [eth_board::probe_value $vio status_sync vio_input INPUT_VALUE 5]
                set echo [eth_board::probe_value $vio echo_enable vio_output OUTPUT_VALUE 1]
                set request [eth_board::probe_value $vio phy_request vio_output OUTPUT_VALUE 1]
                set value [expr {($sync << 4) | ($axi_error << 3) | ($settled << 2) |
                                 ($phy_reset << 1) | $locked}]
                puts [format "STATUS_HEX 0x%08x" $value]
                puts "STATUS_BITS locked=$locked phy_reset_released=$phy_reset settled=$settled axi_error=$axi_error echo_enabled=$echo phy_request=$request pcs=[format 0x%04x [expr {($value >> 8) & 0xffff}]]"
                puts "MANAGEMENT_AXI $axi PROTOCOL=[get_property PROTOCOL $axi]"
                if {($value & 7) != 7 || $axi_error != 0 || $echo != 0 || $request != 0} {
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
