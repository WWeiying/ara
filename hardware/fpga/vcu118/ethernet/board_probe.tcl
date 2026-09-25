# Program one verified VCU118 image and inspect its debug cores. Hash checks
# and the explicit programming confirmation are enforced by board_probe.py.
namespace eval eth_board {
    variable serial 0
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

    proc axi_word {axi kind address {data -}} {
        variable serial
        if {$address ni {0x500 0x504 0x50c} || $kind ni {READ WRITE}} {
            error "MDIO probe forbids this AXI access"
        }
        if {$kind eq "WRITE"} {
            if {![string is integer -strict $data] || $data < 0 ||
                ($address == 0x500 && $data > 0x7f) ||
                ($address == 0x504 && (($data & 0x1f00c800) != 0x03008800 ||
                                       (($data >> 16) & 31) > 3)) ||
                $address == 0x50c} {
                error "MDIO probe forbids this AXI write"
            }
        } elseif {$data ne "-"} { error "Unexpected read data" }
        set args [list -type $kind -address [format %08x $address] -len 1]
        if {$kind eq "WRITE"} { lappend args -data [format %08x $data] }
        set txn [create_hw_axi_txn eth_mdio_[incr serial] $axi {*}$args]
        set code [catch {
            if {[get_property CMD.SIZE $txn] != 32 || [get_property CMD.LEN $txn] != 1} {
                error "Unexpected AXI word width/length"
            }
            run_hw_axi $txn
            refresh_hw_axi $axi
            set prefix STATUS.AXI_${kind}
            if {[get_property ${prefix}_BUSY $axi] != 0 ||
                [get_property ${prefix}_DONE $axi] != 1} {
                error "AXI $kind did not complete"
            }
            set response [get_property [expr {$kind eq "READ" ? "STATUS.RRESP" : "STATUS.BRESP"}] $axi]
            if {$response ne "OKAY"} { error "AXI $kind at [format 0x%03x $address] returned $response" }
            if {$kind eq "READ"} {
                set raw [string map {_ "" " " "" \n "" \r ""} [get_property DATA $txn]]
                regsub -nocase {^0x} $raw {} raw
                if {![regexp -nocase {^[0-9a-f]{8}$} $raw]} { error "Malformed AXI data: $raw" }
                scan $raw %x result
                set result
            } else { set result - }
        } value options]
        set cleanup [catch {delete_hw_axi_txn $txn} cleanup_value cleanup_options]
        if {$code} { return -options $options $value }
        if {$cleanup} { return -options $cleanup_options $cleanup_value }
        return $value
    }

    proc mdio_ready {axi} {
        for {set attempt 0} {$attempt < 20} {incr attempt} {
            set control [eth_board::axi_word $axi READ 0x504]
            if {$control & 0x80} { return }
            after 10
        }
        error "MDIO ready timeout"
    }

    proc mdio_read {axi phy reg} {
        eth_board::mdio_ready $axi
        set command [expr {($phy << 24) | ($reg << 16) | 0x8800}]
        eth_board::axi_word $axi WRITE 0x504 $command
        eth_board::mdio_ready $axi
        set result [eth_board::axi_word $axi READ 0x50c]
        if {($result & 0x10000) == 0} { error "MDIO read data not ready" }
        return [expr {$result & 0xffff}]
    }

    proc identify_phy {axi} {
        set original [expr {[eth_board::axi_word $axi READ 0x500] & 0x7f}]
        set code [catch {
            # 100 MHz management clock, maximal divider; safely below 2.5 MHz MDC.
            eth_board::axi_word $axi WRITE 0x500 0x7f
            set setup [eth_board::axi_word $axi READ 0x500]
            if {($setup & 0x7f) != 0x7f} { error "MDIO setup readback mismatch" }
            set id1 [eth_board::mdio_read $axi 3 2]
            set id2 [eth_board::mdio_read $axi 3 3]
            puts [format "PHY3_ID 0x%04x 0x%04x" $id1 $id2]
            if {$id1 != 0x2000 || ($id2 & 0xfff0) != 0xa230} {
                error "External PHY 3 is not identified as TI DP83867"
            }
            set bmcr [eth_board::mdio_read $axi 3 0]
            set bmsr_first [eth_board::mdio_read $axi 3 1]
            set bmsr_second [eth_board::mdio_read $axi 3 1]
            puts [format "PHY3_BMCR 0x%04x BMSR_FIRST 0x%04x BMSR_SECOND 0x%04x" $bmcr $bmsr_first $bmsr_second]
            puts "PHY_ID_PASS link_not_validated"
        } value options]
        set restore_code [catch {eth_board::axi_word $axi WRITE 0x500 $original} restore_value restore_options]
        if {$code} { return -options $options $value }
        if {$restore_code} { return -options $restore_options $restore_value }
    }

    proc run {args} {
        if {[llength $args] != 4} {
            error "Usage: board_probe.tcl image.bit image.ltx diagnostic|check|mdio|restore hw_server_url"
        }
        lassign $args bit probes mode server
        if {$mode ni {diagnostic check mdio restore}} { error "Invalid image mode" }
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
            if {$mode in {diagnostic restore}} { set_property PROGRAM.FILE $bit $device }
            set_property PROBES.FILE $probes $device
            if {$mode in {diagnostic restore}} { program_hw_devices $device }
            refresh_hw_device $device
            if {$mode in {check mdio}} { puts "CHECK_ONLY no programming attempted" } else { puts "PROGRAMMED $mode" }
            if {$mode in {diagnostic check mdio}} {
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
                if {$mode eq "mdio"} { eth_board::identify_phy $axi }
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
