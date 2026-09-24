# API/control-flow regression only. This does not model Vivado placement or IP.
set here [file dirname [file normalize [info script]]]
set ::eth_build_library_only 1
source [file join $here .. ethernet build.tcl]
lassign $argv output scenario
file mkdir [file join $output vendor]
set f [open [file join $output vendor fake.v] w]; close $f
set properties [dict create]
set ports {}
set operation_log {}
proc set_property {args} {
    global properties
    if {[lindex $args 0] eq "-dict"} {
        dict for {key value} [lindex $args 1] { dict set properties [lindex $args 2] $key $value }
    } else {
        lassign $args key value objects
        foreach object $objects { dict set properties $object $key $value }
    }
}
proc get_property {key object} {
    global properties scenario
    if {$key eq "STATUS"} { return [expr {$scenario eq "synth_fail" ? "synth_design ERROR" : "synth_design Complete!"}] }
    if {$key eq "SLACK"} { return [expr {$scenario eq "timing_fail" ? -0.01 : 0.1}] }
    if {$key eq "PERIOD"} { return [expr {$object eq "phy_clock" ? 1.6 : $scenario eq "clock_fail" ? 20.0 : 10.0}] }
    if {$scenario eq "pin_fail" && $key eq "PACKAGE_PIN" && $object eq "sgmii_txp"} { return AV20 }
    if {$scenario eq "config_fail" && $key eq "CONFIG.PHY_TYPE"} { return RGMII }
    return [dict get $properties $object $key]
}
proc get_ports {args} {
    if {![llength $args]} { return {clk_in_p clk_in_n sys_rst mgt_clk_p mgt_clk_n sgmii_txp sgmii_txn sgmii_rxp sgmii_rxn mdio mdio_mdc phy_rst_n} }
    return [lindex $args end]
}
proc get_pins {args} {
    if {[lsearch -exact $args -regexp] >= 0} {
        set pattern [lindex $args end]
        if {[string match *wr_rd_addr* $pattern] || [string match *stages_reg* $pattern]} { return {p0 p1 p2 p3 p4 p5} }
        return {sync0 sync1}
    }
    return [lindex $args end]
}
proc get_nets {args} {
    global scenario
    if {[lsearch -exact $args -filter] >= 0} { return [expr {$scenario eq "route_fail" ? "unrouted_net" : ""}] }
    return ctrl_clk
}
proc get_clocks {args} {
    return [expr {[lindex $args end] eq "mgt_clk_p" ? "phy_clock" : "control_clock"}]
}
proc get_cells {args} { return {} }
proc get_drc_violations {args} { global scenario; return [expr {$scenario eq "drc_fail" ? "drc_error" : ""}] }
proc get_projects {args} { return {} }
proc current_project {} { return project }
proc current_fileset {} { return sources_1 }
proc get_runs {name} { return $name }
proc get_ips {{name {eth_j10 eth_jtag eth_vio}}} { return $name }
proc get_debug_cores {name} { return $name }
proc version {args} { global scenario; return [expr {$scenario eq "version_fail" ? "2024.1" : "2020.1"}] }
proc open_run {args} {
    global here
    source [file join $here .. ethernet constraints pins.xdc]
}
proc record_command {name args} { global operation_log; lappend operation_log $name }
foreach command {
    set_param create_project create_ip generate_target create_ip_run add_files
    update_compile_order launch_runs wait_on_run connect_debug_port disconnect_debug_port create_clock
    set_max_delay set_bus_skew set_false_path write_checkpoint close_project
    opt_design place_design phys_opt_design route_design
    report_compile_order report_route_status report_io report_clocks report_clock_interaction
    report_utilization report_timing_summary check_timing report_cdc report_bus_skew
    report_exceptions report_methodology report_drc write_debug_probes write_bitstream
} { interp alias {} $command {} record_command $command }
proc report_ip_status {args} {
    global scenario
    set f [open [lindex $args end] w]
    set license [expr {$scenario eq "license_fail" ? "Design_Linking" : "Bought"}]
    puts $f "| eth_j10 | Synthesis | tri_mode_eth_mac@2015.04 | $license | $license |"
    close $f
}
proc get_timing_paths {args} { return path }
set failed [catch {eth_build::run $output [file join $here .. ethernet] $here 4} message]
if {$scenario eq "success"} {
    if {$failed} { error "Unexpected failure: $message" }
    if {[lindex $operation_log end-1] ne "write_bitstream"} { error "Did not reach bitstream" }
} else {
    if {!$failed} { error "Expected $scenario failure" }
    if {[lsearch -exact $operation_log write_bitstream] >= 0} { error "Bitstream attempted after failure" }
}
puts "PASS $scenario"
