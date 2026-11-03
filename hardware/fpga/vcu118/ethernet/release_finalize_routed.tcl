# Successor for a timing-closed DCP rejected by PSLT-1 after routing recovery.
set ::complete_repair_test_mode true
source [file join [file dirname [info script]] repair_complete_routed.tcl]
namespace eval release_finalize {}
proc release_finalize::optimize {out} {
    set clocks [complete_repair::clock_signature]
    set async [complete_repair::async_signature]
    check_pulsed_latches [file join $out before_finalize] false
    route_design -finalize
    complete_repair::route_integrity
    if {[complete_repair::clock_signature] ne $clocks} {error "Clock definitions changed"}
    if {[complete_repair::async_signature] ne $async} {error "ASYNC_REG inventory changed"}
    check_pulsed_latches [file join $out after_finalize]
}
proc release_finalize::run {mode package out token reference tools} {
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
    rebuild_stage $out open_timing_closed_pslt_rejected_input
    open_checkpoint $checkpoint
    complete_repair::route_integrity
    rebuild_stage $out finalize_useful_skew_configuration
    optimize $out
    global design_top
    write_checkpoint [file join $out ${design_top}_routed.dcp]
    rebuild_stage $out strict_finalized_acceptance
    report_route_status -file [file join $out route_status.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    fpga_run::require_timing [file join $out routed_gate]
    rebuild_stage $out routed_ready_for_audit
    close_design
}
if {![info exists ::release_finalize_test_mode]} {
    if {[catch {
        if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
        release_finalize::run {*}$argv
    } message]} {puts stderr $::errorInfo; exit 1}
    exit 0
}
