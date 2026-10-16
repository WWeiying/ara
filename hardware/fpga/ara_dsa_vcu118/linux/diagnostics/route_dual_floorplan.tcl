# Continue only a setup-clean placement. Never alter timing exceptions here.
namespace eval dual_route {}
proc dual_route::stage {name} {
    set f [open [file join $::out stage.txt] w]
    puts $f $name; close $f
    puts "DUAL_ROUTE $name"; flush stdout
}
proc dual_route::slack {kind} {
    set paths [get_timing_paths -quiet -delay_type $kind -max_paths 1]
    if {[llength $paths]!=1} {error "Missing $kind timing evidence"}
    set value [get_property SLACK $paths]
    if {![fpga_checks::finite $value]} {error "Invalid $kind slack: $value"}
    return $value
}
proc dual_route::require_placed_setup {} {
    if {[slack max] < 0} {error "Placement setup still violates; routing not launched"}
}
proc dual_route::run {checkpoint package tools output {mode place}} {
    if {$mode ni {place routed}} {error "Expected place or routed mode"}
    set ::out $output
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    uplevel #0 [list source [file join $package scripts common.tcl]]
    uplevel #0 [list source [file join $package scripts run_support.tcl]]
    set ::dual_cdc_preflight_library_only true
    uplevel #0 [list source [file join $tools dual_cdc_preflight.tcl]]
    if {[llength [fpga_checks::ddr_channels]]!=4} {error "Audit does not cover both DDR channels"}
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    stage opening_${mode}_checkpoint
    open_checkpoint $checkpoint
    if {$mode eq "place"} {
    report_timing_summary -report_unconstrained -file [file join $::out placed_timing.rpt]
    require_placed_setup
    dual_cdc_preflight [file join $::out constraints_before] false
    stage routing
    route_design
    route_design -finalize
    write_checkpoint [file join $::out routed_before_physopt.dcp]
    report_timing_summary -report_unconstrained -file [file join $::out routed_before_physopt.rpt]
    set setup [slack max]; set hold [slack min]
    # One bounded post-route pass for a small residual, not an automatic search.
    if {$setup < 0 || $hold < 0} {
        if {$setup < -0.1 || $hold < -0.1} {error "Routed deficit needs path review: setup=$setup hold=$hold"}
        stage bounded_postroute_optimization
        phys_opt_design -directive Explore
        if {![report_route_status -boolean_check ROUTED_FULLY]} {route_design}
    }
    write_checkpoint [file join $::out candidate_routed.dcp]
    }
    stage strict_timing_and_constraint_gates
    report_route_status -file [file join $::out route_status.rpt]
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        if {[report_route_status -boolean_check $check]!=$expected} {error "Route integrity failed: $check"}
    }
    dual_cdc_preflight [file join $::out constraints_after] false
    fpga_run::require_timing $::out
    report_bus_skew -file [file join $::out bus_skew.rpt]
    set failures [fpga_checks::skew_failures [fpga_checks::read_report [file join $::out bus_skew.rpt]] true]
    if {[llength $failures]} {error "Bus-skew gate failed: $failures"}
    stage collect_full_review_reports
    report_drc -file [file join $::out drc.rpt]
    report_cdc -details -file [file join $::out cdc.rpt]
    check_timing -verbose -file [file join $::out check_timing.rpt]
    report_timing -delay_type max -max_paths 100 -path_type full_clock_expanded -file [file join $::out setup.rpt]
    report_timing -delay_type min -max_paths 100 -path_type full_clock_expanded -file [file join $::out hold.rpt]
    stage timing_closed_requires_drc_cdc_review_not_bitstream
    close_design
}
if {![info exists ::dual_route_library_only]} {
    if {[catch {
        if {[llength $argv] ni {4 5}} {error "Expected checkpoint package tools output ?place|routed?"}
        dual_route::run {*}$argv
    } message]} {
        puts stderr $::errorInfo
        if {[info exists ::out]} {dual_route::stage stopped_for_review}
        exit 1
    }
    exit 0
}
