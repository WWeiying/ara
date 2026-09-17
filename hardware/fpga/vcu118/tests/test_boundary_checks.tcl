# Control-flow checks only; Vivado is still required for physical acceptance.
source [file join [file dirname [info script]] .. scripts common.tcl]
set dir [file normalize [lindex $argv 0]]
file mkdir $dir
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc option {args name} { return [lindex $args [expr {[lsearch -exact $args $name]+1}]] }
proc get_cells {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {
        return [expr {$::scenario eq "gated_reset" ? "gate" : "power"}]
    }
    set filter [option $args -filter]
    if {[string match *BUFG* $filter]} {
        if {$::scenario eq "por_bufg"} { return i_dram_wrapper/i_ui_por/i_rstgen_bypass/buf }
        if {$::scenario in {auto_bufg reset_bufg bad_driver gated_reset inverted_reset}} {
            return {i_rstgen/i_rstgen_bypass/synch_regs_q[3]_BUFG_inst}
        }
        return {}
    }
    set count [expr {[string match *_src_w/* $filter] || [string match *_dst_w/* $filter] ? 320 : 288}]
    if {$::scenario eq "selector_merge"} { incr count -1 }
    set regs {}; for {set i 0} {$i < $count} {incr i} { lappend regs reg$i }
    return $regs
}
proc get_ports {args} { return [lindex $args end] }
proc get_nets {args} { return [option $args -of_objects] }
proc get_pins {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {
        set object [option $args -of_objects]
        if {[lsearch -exact $args -leaf] >= 0} {
            if {[string match */CE $object]} { return power/P }
            if {$::scenario eq "bad_driver"} { return wrong/Q }
            return {i_rstgen/i_rstgen_bypass/synch_regs_q_reg[3]/Q}
        }
        return $object/[lindex [option $args -filter] end]
    }
    return [lindex $args end]
}
proc get_clocks {args} {
    set pin [option $args -of_objects]
    if {[string match */src_clk_i $pin]} { return ui }
    if {$::scenario eq "wrong_debug_clock" && $pin eq "dbg_hub/clk"} { return ui }
    return soc
}
proc get_timing_paths {args} {
    if {$::scenario eq "no_path"} { return {} }
    return [lindex $args end]
}
proc get_property {key object} {
    if {$::scenario eq "query_error"} { error "query failed" }
    switch $key {
        NAME { return $object }
        REF_NAME {
            if {$object eq "power"} { return VCC }
            if {$object eq "gate"} { return LUT1 }
            return [expr {$::scenario eq "reset_bufg" ? "BUFGCTRL" : "BUFGCE"}]
        }
        IS_CE_INVERTED - IS_I_INVERTED { return [expr {$::scenario eq "inverted_reset"}] }
        PERIOD { return 3.333 }
        IOSTANDARD { return [expr {$::scenario eq "wrong_io" ? "LVCMOS18" : "LVCMOS12"}] }
        SLACK {
            switch $::scenario {
                violated { return -0.1 }
                unconstrained { return inf }
                scientific { return 5e-1 }
                default { return 0.5 }
            }
        }
        REQUIREMENT {
            if {$::scenario eq "infinite_budget"} { return inf }
            if {$::scenario eq "wrong_budget"} { return 1000.0 }
            if {[string match uart* $object]} { return 70.0 }
            if {$object eq "c0_ddr4_reset_n"} { return 3.333 }
            return 20.0
        }
        default { error "Unexpected property $key" }
    }
}
proc report_timing {args} { lappend ::pad_reports [file tail [option $args -file]] }
proc write_constraint_checks {dir routed} {
    return [expr {$::scenario eq "missing_constraints" ? [list "constraint missing"] : {}}]
}
foreach scenario {healthy scientific auto_bufg reset_bufg por_bufg bad_driver gated_reset inverted_reset missing_constraints selector_merge no_path wrong_debug_clock wrong_io violated unconstrained wrong_budget infinite_budget query_error} {
    set pad_reports {}
    set before [lsort [chan names]]
    set failed [catch {write_boundary_checks $dir true} message]
    assert {$failed == ($scenario ni {healthy scientific auto_bufg})} "$scenario: $message"
    assert {[lsort [chan names]] eq $before} "report must close on error"
    if {$scenario in {healthy scientific auto_bufg}} {
        assert {[llength $pad_reports] == 7} "all seven pad budgets reported"
    } elseif {$scenario ne "query_error"} {
        assert {[string match {Physical boundary checks failed:*} $message]} "fail-closed route gate"
        assert {[catch {write_boundary_checks $dir false}] == ($scenario eq "missing_constraints")} \
            "missing constraints fail before routing; estimated slack is diagnostic only"
    }
    puts "PASS boundary $scenario"
}
