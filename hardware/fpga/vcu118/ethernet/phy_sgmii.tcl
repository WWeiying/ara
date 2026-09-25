# Inspect the external DP83867 SGMII state; optionally enable only its 6-wire clock.
set ::eth_board_library_only 1
source [file join [file dirname [info script]] board_probe.tcl]

namespace eval eth_sgmii {
    variable serial 0

    proc axi_write {axi address value} {
        variable serial
        if {$address == 0x508} {
            if {$value ni {0x001f 0x0037 0x00d3 0x401f 0x4000}} {
                error "MDIO data write not permitted: $value"
            }
        } elseif {$address == 0x504} {
            if {$value != 0x030d4800 && $value != 0x030e4800 &&
                $value != 0x030e8800 && $value != 0x03148800 &&
                $value != 0x01008800 && $value != 0x01018800} {
                error "MDIO command not permitted: $value"
            }
        } else { error "AXI write address not permitted: $address" }
        set txn [create_hw_axi_txn eth_sgmii_[incr serial] $axi -type WRITE \
                     -address [format %08x $address] -len 1 -data [format %08x $value]]
        set code [catch {
            if {[get_property CMD.SIZE $txn] != 32 || [get_property CMD.LEN $txn] != 1} {
                error "Unexpected AXI transaction width/length"
            }
            run_hw_axi $txn
            refresh_hw_axi $axi
            if {[get_property STATUS.AXI_WRITE_BUSY $axi] != 0 ||
                [get_property STATUS.AXI_WRITE_DONE $axi] != 1 ||
                [get_property STATUS.BRESP $axi] ne "OKAY"} {
                error "MDIO AXI write failed at $address"
            }
        } result options]
        set cleanup [catch {delete_hw_axi_txn $txn} cleanup_result cleanup_options]
        if {$code} { return -options $options $result }
        if {$cleanup} { return -options $cleanup_options $cleanup_result }
    }

    proc mdio_write {axi reg value} {
        if {$reg ni {13 14}} { error "PHY register write not permitted: $reg" }
        if {$reg == 13 && $value ni {0x001f 0x401f}} {
            error "PHY control value not permitted: $value"
        }
        if {$reg == 14 && $value ni {0x0037 0x00d3 0x4000}} {
            error "PHY data value not permitted: $value"
        }
        eth_board::mdio_ready $axi
        eth_sgmii::axi_write $axi 0x508 $value
        eth_sgmii::axi_write $axi 0x504 [expr {(3 << 24) | ($reg << 16) | 0x4800}]
        eth_board::mdio_ready $axi
    }

    proc mdio_read {axi reg} {
        if {$reg ni {14 20}} { error "PHY register read not permitted: $reg" }
        eth_board::mdio_ready $axi
        eth_sgmii::axi_write $axi 0x504 [expr {(3 << 24) | ($reg << 16) | 0x8800}]
        eth_board::mdio_ready $axi
        set result [eth_board::axi_word $axi READ 0x50c]
        if {($result & 0x10000) == 0} { error "MDIO read data not ready" }
        return [expr {$result & 0xffff}]
    }

    proc pcs_read {axi reg} {
        if {$reg ni {0 1}} { error "PCS register read not permitted: $reg" }
        eth_board::mdio_ready $axi
        eth_sgmii::axi_write $axi 0x504 [expr {(1 << 24) | ($reg << 16) | 0x8800}]
        eth_board::mdio_ready $axi
        set result [eth_board::axi_word $axi READ 0x50c]
        if {($result & 0x10000) == 0} { error "PCS MDIO read data not ready" }
        return [expr {$result & 0xffff}]
    }

    proc extended_read {axi address} {
        if {$address ni {0x0037 0x00d3}} { error "Extended PHY address not permitted: $address" }
        eth_sgmii::mdio_write $axi 13 0x001f
        eth_sgmii::mdio_write $axi 14 $address
        eth_sgmii::mdio_write $axi 13 0x401f
        return [eth_sgmii::mdio_read $axi 14]
    }

    proc status {vio} {
        refresh_hw_vio -update_output_values $vio
        set sync [eth_board::probe_value $vio status_sync vio_input INPUT_VALUE 5]
        set pcs [expr {($sync >> 4) & 0xffff}]
        puts [format "PCS_STATUS 0x%04x LINK=%d SYNC=%d" $pcs [expr {$pcs & 1}] [expr {($pcs >> 1) & 1}]]
        return $pcs
    }

    proc sample_clock {vio} {
        set samples {}
        for {set attempt 0} {$attempt < 4} {incr attempt} {
            refresh_hw_vio -update_output_values $vio
            lappend samples [eth_board::probe_value $vio tx_beat_sync vio_input INPUT_VALUE 1]
            after 250
        }
        puts "TX_CLOCK_SAMPLES $samples"
        puts "TX_CLOCK_MOVING [expr {[llength [lsort -unique $samples]] > 1}]"
    }

    proc pulse_pcs_reset {vio} {
        set matches {}
        foreach probe [get_hw_probes -of_objects $vio] {
            if {[get_property NAME $probe] eq "pcs_request" &&
                [get_property TYPE $probe] eq "vio_output"} { lappend matches $probe }
        }
        set request [eth_board::one $matches "PCS-reset VIO probe"]
        if {[eth_board::probe_value $vio pcs_request vio_output OUTPUT_VALUE 1] != 0} {
            error "PCS reset request already asserted"
        }
        set code [catch {
            set_property OUTPUT_VALUE 1 $request
            commit_hw_vio $vio
            after 100
            refresh_hw_vio -update_output_values $vio
            if {[eth_board::probe_value $vio pcs_request vio_output OUTPUT_VALUE 1] != 1 ||
                [eth_board::probe_value $vio phy_rst_n_OBUF vio_input INPUT_VALUE 1] != 1} {
                error "PCS reset assertion failed or external PHY reset changed"
            }
        } message options]
        set release_code [catch {
            set_property OUTPUT_VALUE 0 $request
            commit_hw_vio $vio
            after 100
            refresh_hw_vio -update_output_values $vio
            if {[eth_board::probe_value $vio pcs_request vio_output OUTPUT_VALUE 1] != 0 ||
                [eth_board::probe_value $vio phy_rst_n_OBUF vio_input INPUT_VALUE 1] != 1} {
                error "PCS reset release failed or external PHY reset changed"
            }
        } release_message release_options]
        if {$code} { return -options $options $message }
        if {$release_code} { return -options $release_options $release_message }
        puts "PCS_RESET_PULSE_COMPLETE external_phy_reset_unchanged"
    }

    proc run {args} {
        if {[llength $args] != 3} { error "Usage: phy_sgmii.tcl image.ltx inspect|repair|pcs-reset hw_server_url" }
        lassign $args probes mode server
        if {$mode ni {inspect repair pcs-reset} || ![file isfile $probes]} { error "Invalid mode or probes file" }
        set manager_open 0
        set server_connected 0
        set target_open 0
        set setup_saved 0
        set code [catch {
            open_hw_manager
            set manager_open 1
            connect_hw_server -url $server
            set server_connected 1
            set target [eth_board::one [get_hw_targets] "JTAG target"]
            open_hw_target $target
            set target_open 1
            set device [eth_board::one [get_hw_devices -of_objects $target -filter {PART =~ xcvu9p*}] "xcvu9p device"]
            current_hw_device $device
            set_property PROBES.FILE $probes $device
            refresh_hw_device $device
            set vio [eth_board::one [get_hw_vios -of_objects $device] "diagnostic VIO"]
            set cell [string map {. /} [get_property CELL_NAME $vio]]
            if {![string match "*/i_vio" "/$cell"]} { error "Unexpected VIO cell: $cell" }
            set matches {}
            foreach axi [get_hw_axis -of_objects $device] {
                set cell [string map {. /} [get_property CELL_NAME $axi]]
                if {[string match "*/i_jtag" "/$cell"]} { lappend matches $axi }
            }
            set axi [eth_board::one $matches "diagnostic management AXI"]
            if {[get_property PROTOCOL $axi] ne "AXI4_Lite"} { error "Unexpected AXI protocol" }
            refresh_hw_vio -update_output_values $vio
            foreach {name expected} {locked 1 phy_rst_n_OBUF 1 phy_settled 1 response_error 0} {
                if {[eth_board::probe_value $vio $name vio_input INPUT_VALUE 1] != $expected} {
                    error "Diagnostic baseline failed: $name"
                }
            }
            foreach name {phy_request echo_enable} {
                if {[eth_board::probe_value $vio $name vio_output OUTPUT_VALUE 1] != 0} {
                    error "Diagnostic control unexpectedly enabled: $name"
                }
            }
            set original [expr {[eth_board::axi_word $axi READ 0x500] & 0x7f}]
            set setup_saved 1
            eth_board::axi_word $axi WRITE 0x500 0x7f
            if {([eth_board::axi_word $axi READ 0x500] & 0x7f) != 0x7f} {
                error "MDIO setup readback mismatch"
            }
            set id1 [eth_board::mdio_read $axi 3 2]
            set id2 [eth_board::mdio_read $axi 3 3]
            if {$id1 != 0x2000 || ($id2 & 0xfff0) != 0xa230} {
                error [format "Unexpected external PHY: 0x%04x 0x%04x" $id1 $id2]
            }
            puts [format "PHY_ID 0x%04x 0x%04x" $id1 $id2]
            set bmcr [eth_board::mdio_read $axi 3 0]
            eth_board::mdio_read $axi 3 1
            set bmsr [eth_board::mdio_read $axi 3 1]
            set cfg2 [eth_sgmii::mdio_read $axi 20]
            set aneg [eth_sgmii::extended_read $axi 0x0037]
            set d3 [eth_sgmii::extended_read $axi 0x00d3]
            puts [format "PHY_STATE BMCR=0x%04x BMSR=0x%04x CFG2=0x%04x SGMII_ANEG=0x%04x D3=0x%04x" $bmcr $bmsr $cfg2 $aneg $d3]
            set pcs [eth_sgmii::status $vio]
            eth_sgmii::sample_clock $vio
            set pcs_control [eth_sgmii::pcs_read $axi 0]
            eth_sgmii::pcs_read $axi 1
            set pcs_status [eth_sgmii::pcs_read $axi 1]
            puts [format "PCS_MDIO CONTROL=0x%04x STATUS=0x%04x" $pcs_control $pcs_status]
            if {$mode eq "repair"} {
                if {($d3 & 0x4000) != 0} { error "Six-wire mode already enabled; no write attempted" }
                if {$d3 != 0 || ($cfg2 & 0x80) == 0 || ($bmcr & 0x5000) != 0x1000 ||
                    ($bmsr & 0x24) != 0x24 || ($pcs & 3) == 3} {
                    error "Six-wire repair preconditions not met; no write attempted"
                }
                eth_sgmii::mdio_write $axi 13 0x001f
                eth_sgmii::mdio_write $axi 14 0x00d3
                eth_sgmii::mdio_write $axi 13 0x401f
                eth_sgmii::mdio_write $axi 14 0x4000
                set after_d3 [eth_sgmii::extended_read $axi 0x00d3]
                puts [format "PHY_D3_AFTER 0x%04x" $after_d3]
                if {$after_d3 != 0x4000} { error "Six-wire mode readback failed" }
                for {set attempt 0} {$attempt < 20} {incr attempt} {
                    after 500
                    set pcs [eth_sgmii::status $vio]
                    if {($pcs & 3) == 3} { break }
                }
                eth_sgmii::sample_clock $vio
                set aneg [eth_sgmii::extended_read $axi 0x0037]
                puts [format "PHY_SGMII_ANEG_AFTER 0x%04x" $aneg]
                if {($pcs & 3) != 3} { error "Six-wire configured but PCS link/sync still down" }
                puts "SGMII_LINK_PASS"
            } elseif {$mode eq "pcs-reset"} {
                if {$d3 != 0x4000 || ($cfg2 & 0x80) == 0 ||
                    ($bmsr & 0x24) != 0x24 || ($pcs & 3) == 3} {
                    error "PCS-reset preconditions not met; no pulse attempted"
                }
                eth_sgmii::pulse_pcs_reset $vio
                for {set attempt 0} {$attempt < 20} {incr attempt} {
                    after 500
                    set pcs [eth_sgmii::status $vio]
                    if {($pcs & 3) == 3} { break }
                }
                eth_sgmii::sample_clock $vio
                eth_board::axi_word $axi WRITE 0x500 0x7f
                set d3_after [eth_sgmii::extended_read $axi 0x00d3]
                set aneg_after [eth_sgmii::extended_read $axi 0x0037]
                puts [format "PHY_AFTER_PCS_RESET D3=0x%04x SGMII_ANEG=0x%04x" $d3_after $aneg_after]
                if {$d3_after != 0x4000} { error "External PHY six-wire mode changed during PCS reset" }
                if {($pcs & 3) != 3} { error "PCS reset completed but link/sync still down" }
                puts "SGMII_LINK_PASS"
            } else { puts "SGMII_INSPECTION_COMPLETE" }
        } message options]
        if {$setup_saved} {
            set restore_code [catch {eth_board::axi_word $axi WRITE 0x500 $original} restore_message restore_options]
            if {!$code && $restore_code} {
                set code $restore_code
                set message $restore_message
                set options $restore_options
            }
        }
        if {$target_open} { catch {close_hw_target} }
        if {$server_connected} { catch {disconnect_hw_server} }
        if {$manager_open} { catch {close_hw_manager} }
        if {$code} { return -options $options $message }
    }
}

if {![info exists ::eth_sgmii_library_only]} {
    if {[catch {eth_sgmii::run {*}$argv} message options]} {
        puts stderr "ETH_SGMII_ERROR $message"
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
