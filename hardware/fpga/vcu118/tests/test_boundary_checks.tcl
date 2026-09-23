# Control-flow checks only; Vivado is still required for physical acceptance.
source [file join [file dirname [info script]] .. scripts common.tcl]
set dir [file normalize [lindex $argv 0]]
file mkdir $dir
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc option {args name} { return [lindex $args [expr {[lsearch -exact $args $name]+1}]] }
set reset_scenarios {
    empty_cell_inversion auto_bufg legacy_bufg ui_bufg board_por_bufg
    board_por_bad_driver reset_bufg por_bufg bad_driver gated_reset inverted_reset multiple_ce_drivers missing_ce_driver
    missing_ce_cell multiple_ce_cells
}
foreach pin {I CE} {
    foreach kind {one empty invalid error missing multiple false} {
        lappend reset_scenarios pin_${pin}_$kind
    }
}
proc get_cells {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {
        assert {[llength [option $args -of_objects]] > 0} "no empty driver query"
        if {$::scenario eq "missing_ce_cell"} { return {} }
        if {$::scenario eq "multiple_ce_cells"} { return {power other_power} }
        return [expr {$::scenario eq "gated_reset" ? "gate" : "power"}]
    }
    set filter [option $args -filter]
    if {[string match *BUFG* $filter]} {
        if {$::scenario eq "por_bufg"} { return i_dram_wrapper/i_ui_por/i_rstgen_bypass/buf }
        if {$::scenario in {board_por_bufg board_por_bad_driver}} {
            return {i_board_por/i_rstgen_bypass/synch_regs_q_reg[3]_bufg_place}
        }
        if {$::scenario eq "ui_bufg"} {
            return {i_dram_wrapper/i_ui_rstgen/i_rstgen_bypass/synch_regs_q[3]_BUFG_inst}
        }
        if {$::scenario in $::reset_scenarios} {
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
proc get_nets {args} {
    set object [option $args -of_objects]
    assert {[llength $object] == 1} "query only one known buffer pin"
    return $object
}
proc get_pins {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {
        set object [option $args -of_objects]
        if {[lsearch -exact $args -leaf] >= 0} {
            if {[string match */CE $object]} {
                if {$::scenario eq "multiple_ce_drivers"} { return {power/P power/OTHER} }
                if {$::scenario eq "missing_ce_driver"} { return {} }
                return power/P
            }
            if {$::scenario in {bad_driver board_por_bad_driver}} { return wrong/Q }
            if {$::scenario eq "board_por_bufg"} {
                return {i_board_por/i_rstgen_bypass/synch_regs_q_reg[3]/Q}
            }
            if {$::scenario eq "ui_bufg"} {
                return {i_dram_wrapper/i_ui_rstgen/i_rstgen_bypass/synch_regs_q_reg[3]/Q}
            }
            return {i_rstgen/i_rstgen_bypass/synch_regs_q_reg[3]/Q}
        }
        set pin [lindex [option $args -filter] end]
        if {$::scenario eq "pin_${pin}_missing"} { return {} }
        if {$::scenario eq "pin_${pin}_multiple"} { return [list $object/$pin other/$pin] }
        return $object/$pin
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
            if {$::scenario eq "legacy_bufg"} { return BUFG }
            return [expr {$::scenario eq "reset_bufg" ? "BUFGCTRL" : "BUFGCE"}]
        }
        IS_CE_INVERTED - IS_I_INVERTED {
            incr ::cell_inversion_queries
            if {$::scenario eq "empty_cell_inversion"} { return {} }
            return [expr {$::scenario eq "inverted_reset"}]
        }
        IS_INVERTED {
            set pin [file tail $object]
            assert {$pin in {I CE}} "inversion must be queried on a pin, not a cell"
            lappend ::inversion_queries $pin
            if {$::scenario eq "pin_${pin}_one" || $::scenario eq "inverted_reset"} { return 1 }
            if {$::scenario eq "pin_${pin}_empty"} { return {} }
            if {$::scenario eq "pin_${pin}_invalid"} { return unknown }
            if {$::scenario eq "pin_${pin}_error"} { error "pin query failed" }
            if {$::scenario eq "pin_${pin}_false"} { return FALSE }
            return 0
        }
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
set passing {healthy scientific auto_bufg legacy_bufg ui_bufg board_por_bufg empty_cell_inversion pin_I_false pin_CE_false}
foreach scenario [concat $reset_scenarios {
    healthy scientific missing_constraints selector_merge no_path wrong_debug_clock
    wrong_io violated unconstrained wrong_budget infinite_budget query_error
}] {
    set pad_reports {}
    set inversion_queries {}
    set cell_inversion_queries 0
    set before [lsort [chan names]]
    set failed [catch {write_boundary_checks $dir true} message]
    assert {$failed == ($scenario ni $passing)} "$scenario: $message"
    assert {[lsort [chan names]] eq $before} "report must close on error"
    if {$scenario in $passing} {
        assert {[llength $pad_reports] == 7} "all seven pad budgets reported"
        if {$scenario in $reset_scenarios} {
            set expected [expr {$scenario eq "legacy_bufg" ? {I} : {I CE}}]
            assert {$inversion_queries eq $expected} "query each reset buffer input inversion"
        }
    } elseif {$scenario ne "query_error"} {
        assert {[string match {Physical boundary checks failed:*} $message]} "fail-closed route gate"
        assert {[catch {write_boundary_checks $dir false}] == ($scenario eq "missing_constraints")} \
            "missing constraints fail before routing; estimated slack is diagnostic only"
    }
    assert {$cell_inversion_queries == 0} "do not query optional cell inversion attributes"
    if {$scenario in $reset_scenarios && $scenario ni {reset_bufg por_bufg}} {
        set file [open [file join $dir boundary_checks.rpt] r]
        set report [read $file]
        close $file
        assert {[string match *FAILURES=* $report]} "finish diagnostics even on an invalid pin property"
        assert {[llength $pad_reports] >= 7} "reset failure must not skip other boundary checks"
        if {$scenario in $passing} {
            assert {[string match *IS_INVERTED=* $report]} "record the checked inversion value"
        }
    }
    puts "PASS boundary $scenario"
}
