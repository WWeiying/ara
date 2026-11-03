# WNS-directed successor. On fully routed input, -tns_cleanup suppresses
# the requested Explore pass (2020.1 Route 35-558); do not combine them.
set ::complete_repair_test_mode true
source [file join [file dirname [info script]] repair_complete_routed.tcl]
namespace eval routed_wns {}
proc routed_wns::optimize {} {
    set async_before [complete_repair::async_signature]
    set clocks_before [complete_repair::clock_signature]
    route_design -directive Explore
    complete_repair::route_integrity
    if {[complete_repair::async_signature] ne $async_before} {error "ASYNC_REG inventory changed"}
    if {[complete_repair::clock_signature] ne $clocks_before} {error "Clock definitions changed"}
    puts "WNS_ROUTE_INVARIANTS_PASS"
}
proc routed_wns::run {mode package out token reference tools} {
    if {$mode ne "impl_existing"} {error "Only preserved routed input is supported"}
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    set ::rebuild_test_mode true
    source [file join $package ethernet rebuild_mainrtl_v3.tcl]
    foreach library {common.tcl run_support.tcl} {
        uplevel #0 [list source [file join $package scripts $library]]
    }
    set f [open [file join $tools accepted_routed.txt] r]
    set checkpoint [string trim [read $f]]
    close $f
    fpga_run::nonempty $checkpoint
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    rebuild_stage $out open_preserved_routed_no_reference_reload
    open_checkpoint $checkpoint
    complete_repair::route_integrity
    rebuild_stage $out review_current_failing_endpoints
    complete_repair::review [file join $tools reviewed_endpoints.txt] $out
    # Preserve the checkpoint's physical state. No synthesis, placement,
    # self-reference matching, blanket unroute, or timing-exception changes.
    rebuild_stage $out wns_directed_routing_not_tns_only
    optimize
    global design_top
    write_checkpoint [file join $out ${design_top}_routed.dcp]
    rebuild_stage $out strict_routed_acceptance
    report_route_status -file [file join $out route_status.rpt]
    report_timing -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1 -file [file join $out remaining_setup.rpt]
    rebuild_domain_timing [file join $out routed_domains]
    report_bus_skew -file [file join $out bus_skew.rpt]
    fpga_run::require_timing [file join $out routed_gate]
    rebuild_stage $out routed_ready_for_audit
    close_design
}
if {![info exists ::routed_wns_test_mode]} {
    if {[catch {
        if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
        routed_wns::run {*}$argv
    } message]} {puts stderr $::errorInfo; exit 1}
    exit 0
}
