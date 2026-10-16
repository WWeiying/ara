# Offline control-flow checks, not Vivado timing or routing simulation.
set here [file dirname [info script]]
source [file join $here .. scripts common.tcl]
source [file join $here .. scripts run_support.tcl]
source [file join $here .. scripts continue_physical_support.tcl]
set sandbox [file normalize [lindex $argv 0]]
if {$sandbox eq "" || [file exists $sandbox]} { error "Supply a new output directory" }
file mkdir $sandbox
set fpga_profile host_ethernet
set phase synthesis
namespace eval fpga_warning_details {}
proc fpga_warning_details::write {dir} {}
proc open_package_project {} {}
proc set_param {args} {}
proc fpga_run::check_ips {} {}
proc fpga_run::reusable {args} {}
proc open_run {name} {set ::phase [expr {[string match synth_* $name] ? "synthesis" : "routed"}]}
proc require_no_multiple_drivers {dir} {if {$::scenario eq "drivers"} {error "multiple drivers"}}
proc require_no_combinational_loops {dir} {if {$::scenario eq "loop"} {error "loop"}}
proc get_timing_paths {args} {return path}
proc get_property {key object} {
    if {$key ne "SLACK"} {error "Unexpected property $key"}
    return [expr {$::scenario eq "setup" ? -0.01 : 0.501}]
}
proc close_design {} {}
proc close_project {} {}
proc fpga_run::clone_run {base name parent} {
    if {$base ne "impl_1" || ![string match synth_* $parent]} {error "Not implementation reuse"}
    return $name
}
proc set_property {key value object} {dict set ::properties $key $value}
proc current_run {args} {}
proc launch_runs {name args} {
    if {![string match impl_* $name] || [lrange $args end-1 end] ne {-to_step route_design}} {error "Wrong launch"}
    incr ::launches
}
proc fpga_run::wait_checked {args} {}
proc check_run {args} {}
proc report_route_status {args} {
    if {[lindex $args 0] eq "-file"} {return}
    if {$::scenario eq "unrouted"} {return 0}
    return [expr {[lindex $args 1] eq "ROUTED_FULLY"}]
}
proc put {path text} {set f [open $path w]; puts $f $text; close $f}
proc write_reports {dir routed} {
    if {!$routed} {error "Not routed checks"}
    set timing ""
    foreach check {no_clock unconstrained_internal_endpoints multiple_clock generated_clocks loops latch_loops} {
        append timing "checking $check ([expr {$::scenario eq "coverage" && $check eq "no_clock" ? 1 : 0}])\n"
    }
    put [file join $dir check_timing.rpt] $timing
    set cdc "ID Severity Count Description\nCDC-3 Info 4 Synchronized"
    if {$::scenario eq "cdc"} {append cdc "\nCDC-1 Critical 1 Unknown"}
    if {$::scenario eq "cdc_warning"} {append cdc "\nCDC-15 Warning 1 Enable"}
    if {$::scenario eq "missing_cdc"} {set cdc ""}
    put [file join $dir cdc.rpt] $cdc
    foreach name {drc methodology} {
        put [file join $dir $name.rpt] "Violations found: [expr {$::scenario eq $name ? 1 : 0}]"
    }
}
proc report_timing_summary {args} {
    if {$::phase ne "routed"} {error "Strict summary gate must follow route"}
    set hold [expr {$::scenario eq "hold" ? -0.1 : 0.1}]
    set pulse [expr {$::scenario eq "skew" ? -0.01 : 0.2}]
    return "WNS(ns) TNS Failing Total WHS(ns) THS Failing Total WPWS(ns) TPWS Failing Total\n0.5 0 0 100 $hold 0 0 100 $pulse 0 0 100"
}
proc write_debug_probes {path} {put $path probes}
proc write_bitstream {path} {incr ::bits; put $path bitstream}
set cases {clean setup drivers loop unrouted hold skew coverage cdc cdc_warning missing_cdc drc methodology}
foreach scenario $cases {
    set phase synthesis
    set launches 0
    set bits 0
    set properties {}
    set session [file join $sandbox $scenario]
    file mkdir $session
    set failed [catch {fpga_physical::execute package synth_3aac2309e5ae $session 123456abcdef} message]
    set review [expr {$scenario in {coverage cdc cdc_warning drc methodology}}]
    set expected_error [expr {$scenario ne "clean" && !$review}]
    if {$failed != $expected_error} {error "$scenario: unexpected error=$failed $message"}
    if {$bits != ($scenario eq "clean")} {error "$scenario: unsafe bitstream generation"}
    if {$launches != ($scenario ni {setup drivers loop})} {error "$scenario: unexpected launch"}
    if {$review && ![file exists [file join $session review_required.txt]]} {error "Missing review record"}
    if {$launches && [dict get $properties STEPS.PHYS_OPT_DESIGN.ARGS.DIRECTIVE] ne "ExploreWithAggressiveHoldFix"} {
        error "Missing hold repair directive"
    }
    if {$launches && [dict get $properties STEPS.PLACE_DESIGN.ARGS.DIRECTIVE] ne "ExtraNetDelay_high"} {
        error "Missing net-delay placement directive"
    }
}
puts "PASS: [llength $cases] continuation scenarios; only clean routed reports allow bitgen"
