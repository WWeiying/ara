namespace eval eth_build { variable log; variable stages }
proc eth_build::note {line} {
    variable log
    puts $log $line
    flush $log
    puts $line
}
proc eth_build::step {name body} {
    variable stages
    note "BEGIN $name"
    if {[catch {uplevel 1 $body} result options]} {
        puts $stages "$name\tFAIL"
        flush $stages
        note [dict get $options -errorinfo]
        return -options $options $result
    }
    puts $stages "$name\tPASS"
    flush $stages
    note "END $name"
}
proc eth_build::require_config {ip config} {
    set_property -dict $config $ip
    dict for {key value} $config {
        set actual [get_property $key $ip]
        note "CONFIG $ip $key=$actual EXPECTED=$value"
        if {![eth_preflight::same $actual $value]} { error "IP configuration mismatch: $key" }
    }
}
proc eth_build::full_license {path} {
    set channel [open $path r]
    set content [read $channel]
    close $channel
    set instance ""
    set target ""
    set count 0
    foreach line [split $content \n] {
        set columns [split $line |]
        if {[llength $columns] != 7} { continue }
        set fields {}
        foreach column [lrange $columns 1 5] { lappend fields [string trim $column] }
        lassign $fields inst targ feature generated available
        if {$inst ne ""} { set instance $inst; set target $targ }
        if {$targ ne ""} { set target $targ }
        if {$instance ne "eth_j10" || $target ne "Synthesis" || ![string match tri_mode_eth_mac@* $feature]} { continue }
        incr count
        if {$generated ni {Full Bought Purchased} || $available ni {Full Bought Purchased}} {
            error "TEMAC full license not reported: generated=$generated available=$available"
        }
    }
    if {!$count} { error "TEMAC Synthesis license row not found; inspect ip_status.rpt" }
    note "FULL_LICENSE_REPORTED_NOT_YET_BITSTREAM_VERIFIED"
}
proc eth_build::blackboxes {phase {allow_pending_hub false}} {
    set allowed ""
    if {$allow_pending_hub} {
        set hub [get_debug_cores -quiet dbg_hub]
        if {[llength $hub] != 1 || [get_property NAME $hub] ne "dbg_hub"} {
            error "Expected exactly one registered dbg_hub debug core"
        }
        # Vivado leaves the registered hub as a stub until opt_design. This is
        # not an exemption for other IP, similarly named cells, or routed logic.
        set allowed dbg_hub
    }
    set unresolved {}
    set cells [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}]
    foreach cell $cells {
        if {[get_property NAME $cell] ne $allowed} { lappend unresolved $cell }
    }
    note "BLACKBOX_CHECK $phase COUNT=[llength $cells] CELLS=$cells"
    if {[llength $unresolved]} { error "Unresolved blackboxes ($phase): $unresolved" }
}
proc eth_build::pins {} {
    foreach {port pin standard} {
        clk_in_p G31 DIFF_SSTL12 clk_in_n F31 DIFF_SSTL12 sys_rst L19 LVCMOS12
        mgt_clk_p AT22 LVDS mgt_clk_n AU22 LVDS
        sgmii_txp AU21 DIFF_HSTL_I_DCI_18 sgmii_txn AV21 DIFF_HSTL_I_DCI_18
        sgmii_rxp AU24 DIFF_HSTL_I_DCI_18 sgmii_rxn AV24 DIFF_HSTL_I_DCI_18
        mdio AR23 LVCMOS18 mdio_mdc AV23 LVCMOS18 phy_rst_n BA21 LVCMOS18
    } {
        set object [get_ports $port]
        if {[llength $object] != 1 || [get_property PACKAGE_PIN $object] ne $pin ||
            [get_property IOSTANDARD $object] ne $standard} { error "Pin/standard mismatch: $port" }
        note "PIN $port $pin $standard"
    }
    if {[llength [get_ports]] != 12} { error "Unexpected top-level ports" }
    foreach {port property expected} {
        sgmii_txp OUTPUT_IMPEDANCE RDRV_48_48 sgmii_txn OUTPUT_IMPEDANCE RDRV_48_48
        sgmii_rxp ODT RTT_48 sgmii_rxn ODT RTT_48
        mgt_clk_p DIFF_TERM_ADV TERM_100 mgt_clk_n DIFF_TERM_ADV TERM_100
    } {
        if {![eth_preflight::same [get_property $property [get_ports $port]] $expected]} {
            error "Electrical property mismatch: $port $property"
        }
    }
}
proc eth_build::run {output source board_repo jobs} {
    variable log
    variable stages
    set log [open [file join $output build.rpt] {WRONLY CREAT EXCL}]
    set stages [open [file join $output build_stages.tsv] {WRONLY CREAT EXCL}]
    set ::eth_preflight_library_only 1
    source [file join $source .. tests host_ethernet_preflight.tcl]
    step project {
        if {[version -short] ne "2020.1"} { error "Only reviewed Vivado 2020.1 supported" }
        if {[llength [get_projects -quiet]]} { error "Need fresh batch process" }
        if {![string is integer -strict $jobs] || $jobs < 1 || $jobs > 8} { error "Invalid jobs" }
        set_param general.maxThreads $jobs
        set_param board.repoPaths [list [file normalize $board_repo]]
        create_project eth_diag [file join $output project] -part xcvu9p-flga2104-2L-e
        set_property board_part xilinx.com:vcu118:part0:2.4 [current_project]
        set_property target_language Verilog [current_project]
    }
    step ip {
        create_ip -vlnv xilinx.com:ip:axi_ethernet:7.2 -module_name eth_j10
        # Same reviewed PHY configuration, except the IP no longer drives board reset.
        require_config [get_ips eth_j10] [dict create \
            CONFIG.PHY_TYPE SGMII CONFIG.ENABLE_LVDS true CONFIG.speed_1_2p5 1G \
            CONFIG.SupportLevel 1 CONFIG.processor_mode false CONFIG.ENABLE_AVB false \
            CONFIG.Enable_1588 false CONFIG.USE_BOARD_FLOW true CONFIG.PHYADDR 1 \
            CONFIG.EnableAsyncSGMII false CONFIG.axiliteclkrate 100 \
            CONFIG.ETHERNET_BOARD_INTERFACE sgmii_lvds CONFIG.MDIO_BOARD_INTERFACE mdio_mdc \
            CONFIG.PHYRST_BOARD_INTERFACE Custom CONFIG.DIFFCLK_BOARD_INTERFACE sgmii_phyclk \
            CONFIG.lvdsclkrate 625 CONFIG.tx_in_upper_nibble false \
            CONFIG.rxnibblebitslice0used false CONFIG.txlane0_placement DIFF_PAIR_2 \
            CONFIG.rxlane0_placement DIFF_PAIR_0]
        create_ip -vlnv xilinx.com:ip:jtag_axi:1.2 -module_name eth_jtag
        require_config [get_ips eth_jtag] [dict create CONFIG.PROTOCOL 2 \
            CONFIG.M_AXI_DATA_WIDTH 32 CONFIG.M_AXI_ADDR_WIDTH 32]
        create_ip -vlnv xilinx.com:ip:vio:3.0 -module_name eth_vio
        require_config [get_ips eth_vio] [dict create CONFIG.C_NUM_PROBE_IN 1 \
            CONFIG.C_PROBE_IN0_WIDTH 32 CONFIG.C_NUM_PROBE_OUT 2 \
            CONFIG.C_PROBE_OUT0_WIDTH 1 CONFIG.C_PROBE_OUT0_INIT_VAL 0x0 \
            CONFIG.C_PROBE_OUT1_WIDTH 1 CONFIG.C_PROBE_OUT1_INIT_VAL 0x0]
        generate_target all [get_ips]
        report_ip_status -license_status -file [file join $output ip_status.rpt]
        full_license [file join $output ip_status.rpt]
        foreach name {eth_j10 eth_jtag eth_vio} { create_ip_run [get_ips $name] }
    }
    step sources {
        add_files [glob [file join $output vendor *.v]]
        add_files [glob [file join $source rtl *.sv]]
        add_files -fileset constrs_1 [file join $source constraints pins.xdc]
        set_property top eth_diag_top [current_fileset]
        update_compile_order -fileset sources_1
        report_compile_order -file [file join $output compile_order.rpt]
    }
    step synthesis {
        launch_runs synth_1 -jobs $jobs
        wait_on_run synth_1
        if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} { error "Synthesis did not complete" }
        open_run synth_1
        blackboxes linked_synthesis true
        pins
        set ctrl [get_nets -of_objects [get_pins i_jtag/aclk]]
        if {[llength $ctrl] != 1} { error "Missing independent control clock net" }
        if {[llength [get_nets -quiet -of_objects [get_pins -quiet dbg_hub/clk]]]} {
            disconnect_debug_port dbg_hub/clk
        }
        connect_debug_port dbg_hub/clk $ctrl
        set_property C_CLK_INPUT_FREQ_HZ 100000000 [get_debug_cores dbg_hub]
        set_property C_ENABLE_CLK_DIVIDER false [get_debug_cores dbg_hub]
        source [file join $source constraints timing.tcl]
        eth_diag_timing
        write_checkpoint [file join $output eth_diag_linked.dcp]
    }
    step implementation {
        opt_design
        blackboxes post_opt
        place_design
        phys_opt_design
        route_design
        write_checkpoint [file join $output eth_diag_routed.dcp]
    }
    step reports {
        report_route_status -file [file join $output route_status.rpt]
        report_io -file [file join $output io.rpt]
        report_clocks -file [file join $output clocks.rpt]
        report_clock_interaction -file [file join $output clock_interaction.rpt]
        report_utilization -file [file join $output utilization.rpt]
        report_timing_summary -delay_type min_max -report_unconstrained -file [file join $output timing.rpt]
        check_timing -verbose -file [file join $output check_timing.rpt]
        report_cdc -details -file [file join $output cdc.rpt]
        report_bus_skew -file [file join $output bus_skew.rpt]
        report_exceptions -coverage -file [file join $output exceptions.rpt]
        report_methodology -file [file join $output methodology.rpt]
        report_drc -name eth_drc -file [file join $output drc.rpt]
    }
    step gates {
        blackboxes routed
        pins
        set bad_routes [get_nets -hier -quiet -filter {ROUTE_STATUS == UNROUTED || ROUTE_STATUS == PARTIAL || ROUTE_STATUS == CONFLICTS || ROUTE_STATUS == ANTENNAS || ROUTE_STATUS == NODRIVER || ROUTE_STATUS == UNPLACED}]
        if {[llength $bad_routes]} { error "Incomplete/invalid routes: [llength $bad_routes]" }
        set errors [get_drc_violations -quiet -name eth_drc -filter {SEVERITY == Error}]
        if {[llength $errors]} { error "DRC errors: $errors" }
        foreach type {max min} {
            set paths [get_timing_paths -delay_type $type -max_paths 1]
            if {[llength $paths] != 1} { error "Missing $type timing path" }
            set slack [get_property SLACK $paths]
            note "TIMING $type SLACK=$slack"
            if {![string is double -strict $slack] || $slack < 0} { error "Negative/invalid $type slack" }
        }
        set reference_clock ""
        foreach pin {i_jtag/aclk i_vio/clk dbg_hub/clk} {
            set clocks [get_clocks -of_objects [get_pins $pin]]
            if {[llength $clocks] != 1 || abs([get_property PERIOD $clocks] - 10.0) > 0.01} {
                error "Management/debug clock not 100 MHz: $pin"
            }
            if {$reference_clock ne "" && $reference_clock ne $clocks} { error "Different management/debug clocks" }
            set reference_clock $clocks
            note "MANAGEMENT_CLOCK $pin $clocks"
        }
        set clocks [get_clocks -of_objects [get_ports mgt_clk_p]]
        if {[llength $clocks] != 1 || abs([get_property PERIOD $clocks] - 1.6) > 0.001} {
            error "Missing/incorrect PHY reference clock"
        }
        note "AUTOMATED_GATES_PASSED MANUAL_CDC_IO_TIMING_REVIEW_REQUIRED"
    }
    step bitstream {
        write_debug_probes [file join $output eth_diag.ltx]
        write_bitstream [file join $output eth_diag.bit]
    }
    note "BUILD_COMPLETE HARDWARE_VERIFIED=false PROGRAMMING_APPROVED=false"
    close_project
    close $stages
    close $log
}
if {![info exists ::eth_build_library_only]} {
    if {[llength $argv] != 4} { error "Usage: build.tcl OUTPUT SOURCE BOARD_REPO JOBS" }
    if {[catch {eth_build::run {*}$argv} message options]} {
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
