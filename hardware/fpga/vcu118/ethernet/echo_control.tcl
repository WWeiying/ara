# Read the isolated diagnostic MAC state and control only its echo VIO bit.
set ::eth_board_library_only 1
source [file join [file dirname [info script]] board_probe.tcl]

namespace eval eth_echo {
    variable serial 0

    proc require_pcs_link {sync} {
        set pcs [expr {($sync >> 4) & 0xffff}]
        if {($pcs & 3) != 3} {
            error [format "SGMII PCS link/sync not ready: status=0x%04x" $pcs]
        }
    }

    proc mac_read {axi address} {
        variable serial
        if {$address ni {0x404 0x408 0x700 0x704 0x708}} {
            error "Echo check forbids AXI address $address"
        }
        set txn [create_hw_axi_txn eth_echo_[incr serial] $axi -type READ \
                     -address [format %08x $address] -len 1]
        set code [catch {
            if {[get_property CMD.SIZE $txn] != 32 || [get_property CMD.LEN $txn] != 1} {
                error "Unexpected AXI transaction width/length"
            }
            run_hw_axi $txn
            refresh_hw_axi $axi
            if {[get_property STATUS.AXI_READ_BUSY $axi] != 0 ||
                [get_property STATUS.AXI_READ_DONE $axi] != 1 ||
                [get_property STATUS.RRESP $axi] ne "OKAY"} {
                error "MAC register read failed at $address"
            }
            set raw [string map {_ "" " " "" \n "" \r ""} [get_property DATA $txn]]
            regsub -nocase {^0x} $raw {} raw
            if {![regexp -nocase {^[0-9a-f]{8}$} $raw]} { error "Malformed AXI data: $raw" }
            scan $raw %x value
            set value
        } value options]
        set cleanup [catch {delete_hw_axi_txn $txn} cleanup_value cleanup_options]
        if {$code} { return -options $options $value }
        if {$cleanup} { return -options $cleanup_options $cleanup_value }
        return $value
    }

    proc run {args} {
        if {[llength $args] != 3} { error "Usage: echo_control.tcl image.ltx on|off|status hw_server_url" }
        lassign $args probes mode server
        if {$mode ni {on off status} || ![file isfile $probes]} { error "Invalid mode or probes file" }
        set manager_open 0
        set server_connected 0
        set target_open 0
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
            set axes {}
            foreach axi [get_hw_axis -of_objects $device] {
                set axi_cell [string map {. /} [get_property CELL_NAME $axi]]
                if {[string match "*/i_jtag" "/$axi_cell"]} { lappend axes $axi }
            }
            set axi [eth_board::one $axes "diagnostic management AXI"]
            if {[get_property PROTOCOL $axi] ne "AXI4_Lite"} { error "Unexpected AXI protocol" }
            refresh_hw_vio -update_output_values $vio
            set locked [eth_board::probe_value $vio locked vio_input INPUT_VALUE 1]
            set phy_reset [eth_board::probe_value $vio phy_rst_n_OBUF vio_input INPUT_VALUE 1]
            set settled [eth_board::probe_value $vio phy_settled vio_input INPUT_VALUE 1]
            set axi_error [eth_board::probe_value $vio response_error vio_input INPUT_VALUE 1]
            set request [eth_board::probe_value $vio phy_request vio_output OUTPUT_VALUE 1]
            set sync [eth_board::probe_value $vio status_sync vio_input INPUT_VALUE 5]
            set rcw [eth_echo::mac_read $axi 0x404]
            set tc [eth_echo::mac_read $axi 0x408]
            set filter [eth_echo::mac_read $axi 0x708]
            set uaw0 [eth_echo::mac_read $axi 0x700]
            set uaw1 [eth_echo::mac_read $axi 0x704]
            puts [format "MAC_CONFIG RCW=0x%08x TC=0x%08x FILTER=0x%08x UAW0=0x%08x UAW1=0x%08x" $rcw $tc $filter $uaw0 $uaw1]
            if {$mode eq "on"} {
                if {!$locked || !$phy_reset || !$settled || $axi_error || $request} {
                    error "Diagnostic clock/reset/AXI baseline failed"
                }
                eth_echo::require_pcs_link $sync
                if {($rcw & 0x30000000) != 0x10000000 ||
                    ($tc & 0x30000000) != 0x10000000} {
                    error "MAC RX/TX disabled or in-band FCS enabled"
                }
                if {($filter & 0x80000000) == 0 &&
                    !($uaw0 == 0x00000002 && ($uaw1 & 0xffff) == 0x1801)} {
                    error "MAC filter will reject diagnostic destination"
                }
            }
            if {$mode ne "status"} {
                set matches {}
                foreach probe [get_hw_probes -of_objects $vio] {
                    if {[get_property NAME $probe] eq "echo_enable" &&
                        [get_property TYPE $probe] eq "vio_output"} { lappend matches $probe }
                }
                set enable [eth_board::one $matches "echo-enable VIO probe"]
                set_property OUTPUT_VALUE [expr {$mode eq "on" ? 1 : 0}] $enable
                commit_hw_vio $vio
                after 100
                refresh_hw_vio -update_output_values $vio
            }
            set sync [eth_board::probe_value $vio status_sync vio_input INPUT_VALUE 5]
            set echo [eth_board::probe_value $vio echo_enable vio_output OUTPUT_VALUE 1]
            puts [format "ECHO_STATUS enable=%d seen=%d sent=%d rejected=%d pcs=0x%04x" \
                      $echo [expr {($sync >> 1) & 1}] [expr {($sync >> 2) & 1}] \
                      [expr {($sync >> 3) & 1}] [expr {($sync >> 4) & 0xffff}]]
            if {($sync & 1) != $echo || ($mode eq "on" && !$echo) ||
                ($mode eq "off" && $echo)} { error "VIO echo control did not take effect" }
        } message options]
        if {$target_open} { catch {close_hw_target} }
        if {$server_connected} { catch {disconnect_hw_server} }
        if {$manager_open} { catch {close_hw_manager} }
        if {$code} { return -options $options $message }
    }
}

if {![info exists ::eth_echo_library_only]} {
    if {[catch {eth_echo::run {*}$argv} message options]} {
        puts stderr "ETH_ECHO_ERROR $message"
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
