# Reuse all existing baseline boundary negative fixtures before testing C2.
set scratch [file normalize [lindex $argv 0]]
source [file join [file dirname [info script]] test_boundary_checks.tcl]
rename get_cells baseline_get_cells
rename get_property baseline_get_property
rename get_pins baseline_get_pins
set case healthy
proc get_cells {args} {
    if {[lsearch -exact $args -of_objects] < 0} {
        set filter [option $args -filter]
        if {[string match *BUFG* $filter] && $::case in {c2_bufg c2_por c2_bad_driver}} {
            set reset [expr {$::case eq "c2_por" ? "i_ui_por" : "i_ui_rstgen"}]
            return gen_ddr2.i_dram_wrapper_c2/$reset/i_rstgen_bypass/buf
        }
        if {[string match *gen_ddr2* $filter] && $::case eq "c2_missing_selector"} { return {} }
    }
    return [baseline_get_cells {*}$args]
}
proc get_property {key object} {
    if {$key eq "REQUIREMENT" && $object eq "c1_ddr4_reset_n"} { return 3.333 }
    if {$key eq "PERIOD" && $object eq "soc"} { return 20.0 }
    if {$key eq "IOSTANDARD" && $object eq "c1_ddr4_reset_n" && $::case eq "c2_wrong_io"} { return LVCMOS18 }
    return [baseline_get_property $key $object]
}
proc get_pins {args} {
    if {[lsearch -exact $args -of_objects] >= 0 && [lsearch -exact $args -leaf] >= 0} {
        set object [option $args -of_objects]
        if {[string match gen_ddr2.*/I $object]} {
            if {$::case eq "c2_bad_driver"} { return other/Q }
            return {gen_ddr2.i_dram_wrapper_c2/i_ui_rstgen/i_rstgen_bypass/synch_regs_q_reg[3]/Q}
        }
    }
    if {[string match gen_host.*/aclk [lindex $args end]] && $::case eq "host_missing_clock"} { return {} }
    return [baseline_get_pins {*}$args]
}
set scenario healthy
set fpga_profile dual_ddr
foreach case {healthy c2_bufg c2_por c2_bad_driver c2_missing_selector c2_wrong_io host_missing_clock} {
    set pad_reports {}
    set failed [catch {write_boundary_checks $scratch true} message]
    assert {$failed == ($case ni {healthy c2_bufg})} "$case: $message"
    assert {[llength $pad_reports] == 8} "both reset pads checked, even on error"
    set report [fpga_checks::read_report $scratch/boundary_checks.rpt]
    assert {[string match {*SELECTOR gen_ddr2.i_dram_wrapper_c2*} $report]} "C2 selectors checked"
    assert {[string match {*HOST_CLOCK jtag_debug=*} $report]} "independent debug bridge clock checked"
    puts "PASS dual boundary $case"
}
