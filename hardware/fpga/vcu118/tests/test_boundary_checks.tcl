# Control-flow checks only; Vivado is still required for physical acceptance.
source [file join [file dirname [info script]] .. scripts common.tcl]
set dir [file normalize [lindex $argv 0]]
file mkdir $dir
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc option {args name} { return [lindex $args [expr {[lsearch -exact $args $name]+1}]] }
proc get_cells {args} {
    set filter [option $args -filter]
    if {[string match *BUFG* $filter]} {
        return [expr {$::scenario eq "reset_bufg" ? "reset/BUFG" : ""}]
    }
    set count [expr {[string match *_src_w/* $filter] || [string match *_dst_w/* $filter] ? 320 : 288}]
    if {$::scenario eq "selector_merge"} { incr count -1 }
    set regs {}; for {set i 0} {$i < $count} {incr i} { lappend regs reg$i }
    return $regs
}
proc get_ports {args} { return [lindex $args end] }
proc get_pins {args} { return [lindex $args end] }
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
foreach scenario {healthy scientific reset_bufg selector_merge no_path wrong_debug_clock wrong_io violated unconstrained wrong_budget infinite_budget query_error} {
    set pad_reports {}
    set before [lsort [chan names]]
    set failed [catch {write_boundary_checks $dir true} message]
    assert {$failed == ($scenario ni {healthy scientific})} "$scenario: $message"
    assert {[lsort [chan names]] eq $before} "report must close on error"
    if {$scenario in {healthy scientific}} {
        assert {[llength $pad_reports] == 7} "all seven pad budgets reported"
    } elseif {$scenario ne "query_error"} {
        assert {[string match {Physical boundary checks failed:*} $message]} "fail-closed route gate"
        assert {![catch {write_boundary_checks $dir false}]} "synthesis collects without route gate"
    }
    puts "PASS boundary $scenario"
}
