# Orchestration mocks: no Vivado or hardware. Effective exceptions have a
# separate test and must also be measured by Vivado on the actual netlist.
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Expected a new directory"}
file mkdir $root
set script [file join [file dirname [info script]] rebuild_dual_cdc.tcl]
rename source real_source
proc source {path} {}
rename exit real_exit
proc exit {code} {return -code error -errorcode [list TEST_EXIT $code] "exit $code"}
proc record {args} {lappend ::calls $args}
namespace eval fpga_run {}
namespace eval fpga_checks {}
foreach name {set_param set_msg_config current_run close_project close_design
              require_no_multiple_drivers require_no_combinational_loops report_timing_summary report_timing
              report_bus_skew open_package_project} {proc $name {args} {}}
proc get_param {name} {return {}}
proc fpga_run::check_ips {} {}
proc fpga_run::reusable {args} {record reusable {*}$args}
proc fpga_run::clone_run {base name parent} {record clone $parent; return $name}
proc fpga_run::require_timing {args} {if {$::scenario eq "timing_fail"} {error "timing"}}
proc fpga_checks::read_report {path} {return test}
proc fpga_checks::skew_failures {args} {return [expr {$::scenario eq "skew_fail" ? "violation" : ""}]}
proc get_filesets {args} {
    set name [lindex $args end]
    if {$name eq "constrs_1" || [info exists ::files($name)]} {return $name}
    return {}
}
proc create_fileset {flag name} {set ::files($name) {}}
proc get_files {args} {
    set fs [lindex $args [expr {[lsearch -exact $args -of_objects]+1}]]
    if {$fs eq "constrs_1"} {return {old/board.xdc old/ddr2_clock.xdc old/timing.xdc old/ethernet.xdc old/ethernet_timing.tcl old/cdc.xdc}}
    set path [lindex $args end]
    return [expr {$path in $::files($fs) ? $path : ""}]
}
proc add_files {args} {lappend ::files([lindex $args 1]) [lindex $args end]}
proc get_property {key object} {
    switch $key {
        NAME {return $object}
        SLACK {
            if {$object eq "placed_path"} {
                return [expr {$::scenario eq "placed_failure" ? -1.349 : 0.1}]
            }
            return [expr {$::scenario eq "large_failure" ? -1.0 : $::scenario eq "small_failure" ? -0.01 : 0.1}]
        }
        default {return test}
    }
}
proc set_property {args} {record property {*}$args}
proc launch_runs {args} {record launch {*}$args}
proc rebuild_opt_complete {args} {
    if {$::scenario eq "constraint_failure"} {error "constraint error"}
    return optimized.dcp
}
proc open_checkpoint {args} {record open {*}$args}
proc dual_cdc_preflight {args} {
    record check {*}$args
    if {$::scenario eq "serialization_failure"} {error "lost exception"}
}
proc place_design {} {record place}
proc route_design {args} {record route {*}$args}
proc phys_opt_design {args} {record phys_opt {*}$args}
proc write_checkpoint {args} {record checkpoint {*}$args}
proc get_timing_paths {args} {
    if {[lsearch -exact $::calls route]<0} {return placed_path}
    return path
}
proc report_route_status {args} {return [expr {[lindex $args end] eq "ROUTED_FULLY"}]}
foreach scenario {healthy constraint_failure serialization_failure placed_failure large_failure small_failure timing_fail skew_fail} {
    set ::calls {}
    unset -nocomplain ::files
    set out [file join $root $scenario]
    file mkdir $out
    set ::argv [list bundle tools $out abcdef012345]
    set code [catch {real_source $script} message options]
    set expected [expr {$scenario ni {healthy small_failure}}]
    if {!$code || [dict get $options -errorcode] ne [list TEST_EXIT $expected]} {
        error "Unexpected $scenario: $message / $options"
    }
    if {[lsearch -exact $calls {clone synth_903503b5ace4}]<0} {error "Wrong synthesis parent"}
    if {$scenario in {constraint_failure serialization_failure} && [lsearch -exact $calls place]>=0} {
        error "Placed a design with invalid constraints"
    }
    if {$scenario eq "placed_failure"} {
        if {[lsearch -exact $calls route]>=0} {error "Routed a large placed setup failure"}
        if {[lsearch -exact $calls [list checkpoint [file join $out placed.dcp]]]<0} {
            error "Placement was not preserved for diagnosis"
        }
    }
    if {$scenario eq "large_failure" && [lsearch -glob $calls {phys_opt *}]>=0} {
        error "Blind physical retry on large violation"
    }
    if {$scenario eq "small_failure" && [lsearch -glob $calls {phys_opt *}]<0} {error "Missing bounded physical pass"}
    set f [open [file join $out stage.txt] r]; set stage [string trim [read $f]]; close $f
    if {($stage eq "routed_ready_for_full_audit") != !$expected} {error "False completion state"}
    puts "PASS orchestration $scenario"
}
