# Apply standalone loader IO constraints to an existing synthesized netlist.
namespace eval loader_pins {
    proc run {output xdc} {
        if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
        set project [file join $output project eth_loader_bd.xpr]
        if {![file isfile $project] || ![file isfile $xdc]} {
            error "Missing project or XDC"
        }
        open_project $project
        if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {
            error "Synthesis is not complete"
        }
        add_files -fileset constrs_1 $xdc
        open_run synth_1
        set report [open [file join $output pin_audit.txt] {WRONLY CREAT EXCL}]
        foreach {port pin standard} {
            sys_clk_250_clk_p[0] E12 LVDS
            sys_clk_250_clk_n[0] D12 LVDS
            sgmii_phyclk_clk_p AT22 LVDS
            sgmii_phyclk_clk_n AU22 LVDS
            sgmii_lvds_txp AU21 DIFF_HSTL_I_DCI_18
            sgmii_lvds_txn AV21 DIFF_HSTL_I_DCI_18
            sgmii_lvds_rxp AU24 DIFF_HSTL_I_DCI_18
            sgmii_lvds_rxn AV24 DIFF_HSTL_I_DCI_18
            mdio_mdc_mdio_io AR23 LVCMOS18
            mdio_mdc_mdc AV23 LVCMOS18
            phy_reset_out[0] BA21 LVCMOS18
            sys_reset L19 LVCMOS12
        } {
            set object [get_ports -quiet $port]
            if {[llength $object] != 1} { error "Missing top port: $port" }
            set actual_pin [get_property PACKAGE_PIN $object]
            set actual_standard [get_property IOSTANDARD $object]
            if {$actual_pin ne $pin || $actual_standard ne $standard} {
                error "Pin mismatch: $port pin=$actual_pin standard=$actual_standard"
            }
            puts $report "PIN $port $pin $standard"
        }
        foreach {port period} {sys_clk_250_clk_p[0] 4.000} {
            set clocks [get_clocks -of_objects [get_ports $port]]
            if {[llength $clocks] != 1 ||
                abs([get_property PERIOD $clocks] - $period) > 0.01} {
                error "Missing or incorrect clock on $port: $clocks"
            }
            puts $report "CLOCK $port $clocks PERIOD=[get_property PERIOD $clocks]"
        }
        puts $report "PIN_AUDIT_PASS NOT_ROUTE_OR_DRC_PASS"
        close $report
        report_io -file [file join $output io_synth.rpt]
        report_clocks -file [file join $output clocks_synth.rpt]
        close_project
        puts "LOADER_PIN_AUDIT_PASS $output"
    }
}

if {[llength $argv] != 2} { error "Usage: loader_bd_pin_audit.tcl OUTPUT XDC" }
if {[catch {loader_pins::run {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
