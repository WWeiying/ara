set script [file join [file dirname [info script]] place_dual_floorplan.tcl]
rename source real_source
proc source {args} {}
rename exit real_exit
proc exit {code} {return -code error -errorcode [list TEST_EXIT $code] "exit $code"}
namespace eval dual_locality {}
namespace eval dual_floor {}
proc dual_locality::apply_plan {plan file} {
    if {[llength $plan]!=10} {error "Lost original PHY/DDR SLR hints"}
}
proc dual_floor::apply {args} {lappend ::calls floorplan}
proc dual_cdc_preflight {args} {if {$::scenario eq "bad_cdc"} {error "CDC failure"}}
proc check_dual_reset_netlist {args} {if {$::scenario eq "bad_reset"} {error "Reset changed"}}
proc get_param {args} {return {}}
foreach name {set_param open_checkpoint close_design report_timing_summary report_timing report_clock_utilization report_utilization report_design_analysis report_bus_skew report_drc} {
    proc $name {args} {}
}
proc place_design {args} {lappend ::calls place}
proc phys_opt_design {args} {
    if {$args ne {-directive AggressiveFanoutOpt}} {error "Changed physical baseline"}
    lappend ::calls physical
}
proc write_checkpoint {args} {lappend ::calls checkpoint}
set root [file join /tmp dual_floor_flow_test_[pid]]
try {
    foreach scenario {healthy bad_cdc bad_reset} {
        set ::out [file join $root $scenario]; file mkdir $::out
        set argv [list clean_opt.dcp tools package $::out]
        set calls {}
        catch {real_source $script} message options
        set expected [expr {$scenario ne "healthy"}]
        if {[dict get $options -errorcode] ne [list TEST_EXIT $expected]} {error "Bad result: $options"}
        if {$expected && [llength $calls]} {error "Physical work before validation"}
        if {!$expected && $calls ne {floorplan checkpoint place checkpoint physical checkpoint}} {
            error "Wrong flow, repeated placement, or unexpected mutation: $calls"
        }
        puts "PASS $scenario"
    }
} finally {file delete -force $root}
