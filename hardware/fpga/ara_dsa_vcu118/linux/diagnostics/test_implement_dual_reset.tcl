set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Expected new test directory"}
set script [file join [file dirname [info script]] implement_dual_reset.tcl]
rename source real_source
proc source {path} {}
rename exit real_exit
proc exit {code} {return -code error -errorcode [list TEST_EXIT $code] "exit $code"}
proc record {args} {lappend ::calls $args}
namespace eval fpga_run {}
namespace eval fpga_checks {}
namespace eval dual_locality {}
foreach cmd {set_param set_msg_config current_run open_package_project close_design close_project
             require_no_multiple_drivers require_no_combinational_loops report_timing report_timing_summary
             report_bus_skew set_property} {proc $cmd {args} {}}
proc get_param {args} {return {}}
proc open_checkpoint {args} {record open {*}$args}
proc open_run {args} {record open_run {*}$args; set ::phase synth}
proc check_dual_reset_netlist {args} {if {$::scenario eq "bad_reset"} {error "bad reset"}}
proc dual_locality::plan {} {return {{hierarchy SLR2}}}
proc dual_locality::apply_plan {args} {record locality}
proc fpga_run::check_ips {} {}
proc fpga_run::reusable {args} {record reusable {*}$args}
proc fpga_run::clone_run {base name parent} {record parent $parent; return $name}
proc fpga_run::require_timing {args} {if {$::scenario eq "final_timing"} {error "timing fail"}}
proc fpga_checks::finite {value} {return [string is double -strict $value]}
proc fpga_checks::read_report {args} {return report}
proc fpga_checks::skew_failures {args} {return [expr {$::scenario eq "skew" ? "failure" : ""}]}
proc launch_runs {args} {record launch}
proc rebuild_opt_complete {args} {return optimized.dcp}
proc dual_cdc_preflight {args} {if {$::scenario eq "bad_cdc"} {error "missing CDC"}}
proc place_design {} {record place; set ::phase placed}
proc phys_opt_design {args} {record phys {*}$args}
proc write_checkpoint {args} {record checkpoint {*}$args}
proc route_design {args} {record route; set ::phase routed}
proc get_timing_paths {args} {return path}
proc get_property {key obj} {
    if {$key ne "SLACK"} {error "Unexpected property"}
    if {$::scenario eq "bad_setup" && $::phase eq "synth"} {return -0.1}
    if {$::scenario eq "bad_place" && $::phase eq "placed"} {return -0.6}
    if {$::scenario eq "bad_route" && $::phase eq "routed"} {return -0.6}
    if {$::scenario eq "small_route" && $::phase eq "routed"} {return -0.01}
    return 0.1
}
proc report_route_status {args} {
    if {$::scenario eq "route_integrity"} {return 0}
    return [expr {[lindex $args end] eq "ROUTED_FULLY"}]
}
foreach scenario {healthy bad_reset bad_setup bad_cdc bad_place bad_route small_route route_integrity final_timing skew} {
    set ::calls {}
    set ::phase initial
    set dir [file join $root $scenario]
    file mkdir $dir
    set ::argv [list package tools $dir abcdef012345 reference.dcp]
    catch {real_source $script} message options
    set expected [expr {$scenario ni {healthy small_route}}]
    if {[dict get $options -errorcode] ne [list TEST_EXIT $expected]} {error "Unexpected result: $scenario / $options"}
    if {$scenario in {bad_reset bad_setup} && {launch} in $calls} {error "Launched invalid synthesis"}
    if {$scenario eq "bad_cdc" && {place} in $calls} {error "Placed invalid constraints"}
    if {$scenario eq "bad_place" && {route} in $calls} {error "Routed severe placed deficit"}
    if {$scenario eq "bad_route" && {phys -directive Explore} in $calls} {error "Blind routed retry"}
    if {$scenario eq "small_route" && {phys -directive Explore} ni $calls} {error "Missing bounded pass"}
    if {$scenario eq "healthy" && {parent synth_abcdef012345} ni $calls} {error "Wrong synthesized parent"}
    puts "PASS $scenario"
}
