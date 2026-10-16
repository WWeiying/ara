set ::dual_route_library_only true
source [file join [file dirname [info script]] route_dual_floorplan.tcl]
source [file join [file dirname [info script]] .. .. scripts constraint_checks.tcl]
proc get_timing_paths {args} {return $::paths}
proc get_property {args} {return $::value}
foreach {value paths reject} {0 p 0 0.001 p 0 -0.001 p 1 NaN p 1 Inf p 1 0 {} 1 0 {p q} 1} {
    if {[catch {dual_route::require_placed_setup}] != $reject} {error "Gate mismatch: $value / $paths"}
    puts "PASS setup gate $value / $paths"
}
rename source real_source
proc source {args} {
    if {[uplevel 1 {namespace current}] ne "::" || [info level]!=1} {
        error "Frozen package helpers must load in the global context"
    }
}
proc fpga_checks::ddr_channels {} {
    if {$::scenario eq "single_channel_audit"} {return {c1 pad1}}
    return {c1 pad1 c2 pad2}
}
proc fpga_checks::read_report {args} {return report}
proc fpga_checks::skew_failures {args} {
    if {$::scenario eq "skew"} {return violation}
    return {}
}
namespace eval fpga_run {}
proc fpga_run::require_timing {args} {
    if {$::scenario eq "pulse"} {error "Pulse violation"}
}
proc dual_cdc_preflight {args} {
    if {$::scenario eq "cdc"} {error "Lost CDC bound"}
}
proc get_param {args} {return {}}
foreach name {set_param open_checkpoint close_design report_timing_summary report_bus_skew report_drc report_cdc check_timing report_timing} {
    proc $name {args} {}
}
proc get_timing_paths {args} {return [lindex $args 3]}
proc get_property {prop kind} {
    if {$::scenario eq "setup"} {return -0.001}
    if {$::routed && !$::optimized} {
        if {$::scenario eq "large"} {return -0.2}
        if {$::scenario eq "small"} {return -0.01}
    }
    return 0.02
}
proc route_design {args} {incr ::routes; set ::routed 1}
proc write_checkpoint {args} {lappend ::saved [file tail [lindex $args 0]]}
proc report_route_status {args} {
    if {[lindex $args 0] eq "-file"} {return}
    if {[lindex $args end] eq "ERRORS_IN_ROUTES"} {return [expr {$::scenario eq "route_error"}]}
    return 1
}
proc phys_opt_design {args} {set ::optimized 1}
set root [file join /tmp dual_route_test_[pid]]
try {
    foreach scenario {healthy setup cdc large small skew pulse route_error single_channel_audit} {
        set routes 0; set routed 0; set optimized 0; set saved {}
        file mkdir [file join $root $scenario]
        set failed [catch {dual_route::run placed.dcp package tools [file join $root $scenario]} message]
        if {$failed != ($scenario ni {healthy small})} {error "Unexpected $scenario result: $message"}
        if {$scenario in {setup cdc single_channel_audit} && $routes} {error "Route started before gate"}
        if {$optimized != ($scenario eq "small")} {error "Unbounded physical optimization"}
        if {$scenario eq "large" && $saved ne {routed_before_physopt.dcp}} {error "Lost failed candidate"}
        puts "PASS flow $scenario"
    }
} finally {file delete -force $root}
