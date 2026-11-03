# Continue the CURRENT routed design. Importing only DDR roots from an older
# DCP dropped to low reuse in 2020.1 and did not retain reference routing.
set ::complete_repair_test_mode true
source [file join [file dirname [info script]] repair_complete_routed.tcl]
namespace eval self_reference {}

proc self_reference::require_high_reuse {report} {
    if {![regexp {\|[ \t]*Reuse mode[ \t]*\|[ \t]*High[ \t]*\|} $report] ||
        ![regexp {\|[ \t]*Incremental Directive[ \t]*\|[ \t]*TimingClosure[ \t]*\|} $report]} {
        error "TimingClosure high-reuse mode was not established; do not route"
    }
    foreach type {Cells Nets} {
        set pattern [format {\|[ \t]*%s[ \t]*\|[ \t]*([0-9.]+)[ \t]*\|[ \t]*([0-9.]+)[ \t]*\|} $type]
        if {![regexp $pattern $report -> matched reused] ||
            ![string is double -strict $matched] || ![string is double -strict $reused] ||
            $matched < 99.0 || $reused < 99.0 || $matched > 100.0 || $reused > 100.0} {
            error "Current-design self-reference lost $type identity/reuse; do not route"
        }
    }
}

proc self_reference::optimize {checkpoint out} {
    set async_before [complete_repair::async_signature]
    set clocks_before [complete_repair::clock_signature]
    # No old functional netlist, selected-root filter, placement, or timing
    # exception is imported. The reference is the very DCP already open.
    read_checkpoint -incremental -directive TimingClosure $checkpoint
    set path [file join $out self_reuse_before.rpt]
    report_incremental_reuse -file $path
    set f [open $path r]
    set report [read $f]
    close $f
    require_high_reuse $report
    puts "SELF_REFERENCE_HIGH_REUSE_CONFIRMED"
    route_design -directive Explore -tns_cleanup
    complete_repair::route_integrity
    if {[complete_repair::async_signature] ne $async_before} {error "ASYNC_REG inventory changed"}
    if {[complete_repair::clock_signature] ne $clocks_before} {error "Clock definitions changed"}
    puts "SELF_REFERENCE_INVARIANTS_PASS"
}

proc self_reference::run {mode package out token reference tools} {
    if {$mode ne "impl_existing"} {error "Only current routed continuation is supported"}
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
    rebuild_stage $out open_current_routed_no_synthesis_or_placement
    open_checkpoint $checkpoint
    complete_repair::route_integrity
    rebuild_stage $out verify_input_endpoint_inventory
    complete_repair::review [file join $tools reviewed_endpoints.txt] $out
    rebuild_stage $out establish_self_reference_and_repair_routes
    optimize $checkpoint $out
    global design_top
    write_checkpoint [file join $out ${design_top}_routed.dcp]
    rebuild_stage $out strict_routed_acceptance
    report_incremental_reuse -file [file join $out self_reuse_after.rpt]
    report_route_status -file [file join $out route_status.rpt]
    report_timing -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1 -file [file join $out remaining_setup.rpt]
    rebuild_domain_timing [file join $out routed_domains]
    report_bus_skew -file [file join $out bus_skew.rpt]
    fpga_run::require_timing [file join $out routed_gate]
    rebuild_stage $out routed_ready_for_audit
    close_design
}

if {![info exists ::self_reference_test_mode]} {
    if {[catch {
        if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
        self_reference::run {*}$argv
    } message]} {puts stderr $::errorInfo; exit 1}
    exit 0
}
