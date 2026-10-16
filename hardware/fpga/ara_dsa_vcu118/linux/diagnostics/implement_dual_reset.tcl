# Continue verified new synthesis. Prior placement supplies SLR anchors only.
proc reset_impl_stage {name} {
    set f [open [file join $::out stage.txt] w]
    puts $f $name
    close $f
    puts "DUAL_RESET_IMPL $name"
    flush stdout
}
if {[catch {
    if {[llength $argv]!=5} {error "Expected package tools output token anchor_checkpoint"}
    lassign $argv package tools ::out token anchor
    if {![regexp {^[a-f0-9]{12}$} $token]} {error "Invalid synthesis token"}
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    source [file join $package scripts common.tcl]
    source [file join $package scripts run_support.tcl]
    set ::rebuild_test_mode true
    source [file join $tools rebuild_mainrtl.tcl]
    set ::dual_reset_library_only true
    source [file join $tools check_dual_reset_netlist.tcl]
    set ::dual_cdc_preflight_library_only true
    source [file join $tools dual_cdc_preflight.tcl]
    source [file join $tools dual_slr_locality.tcl]
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    set_msg_config -id {Common 17-1548} -new_severity ERROR
    set_msg_config -id {Board 49-67} -new_severity ERROR
    reset_impl_stage read_only_anchor_inventory
    open_checkpoint $anchor
    set plan [dual_locality::plan]
    close_design
    reset_impl_stage verify_current_synthesis
    open_package_project
    fpga_run::check_ips
    set parent synth_$token
    fpga_run::reusable $parent {*synth_design Complete*} ara_dsa_vcu118.dcp
    open_run $parent
    check_dual_reset_netlist $::out
    require_no_multiple_drivers [file join $::out synthesis_gate]
    require_no_combinational_loops [file join $::out synthesis_gate]
    set setup [get_timing_paths -quiet -delay_type max -max_paths 1]
    if {[llength $setup]!=1 || ![fpga_checks::finite [get_property SLACK $setup]] ||
        [get_property SLACK $setup]<0} {error "Synthesis setup failed"}
    close_design
    set name impl_reset_$token
    set run [fpga_run::clone_run impl_1 $name $parent]
    set_property STEPS.OPT_DESIGN.TCL.PRE [file join $tools dual_cdc_preflight.tcl] $run
    current_run -implementation $run
    reset_impl_stage optimize_current_netlist
    launch_runs $name -jobs 1 -dir $::out -to_step opt_design
    set optimized [rebuild_opt_complete $name [file join $::out $name]]
    close_project
    open_checkpoint $optimized
    reset_impl_stage verify_effective_constraints
    dual_cdc_preflight [file join $::out serialized_constraints] false
    require_no_multiple_drivers [file join $::out optimized_gate]
    require_no_combinational_loops [file join $::out optimized_gate]
    dual_locality::apply_plan $plan [file join $::out slr_assignments.tsv]
    reset_impl_stage locality_placement
    place_design
    write_checkpoint [file join $::out placed.dcp]
    # A single measured physical pass; no repeated multi-hour searches.
    reset_impl_stage reset_fanout_optimization
    phys_opt_design -directive AggressiveFanoutOpt
    write_checkpoint [file join $::out fanout_placed.dcp]
    report_timing_summary -report_unconstrained -file [file join $::out placed_timing.rpt]
    report_timing -delay_type max -max_paths 100 -nworst 1 -file [file join $::out placed_setup.rpt]
    report_timing -delay_type min -max_paths 50 -nworst 1 -file [file join $::out placed_hold.rpt]
    set setup [get_timing_paths -quiet -delay_type max -max_paths 1]
    if {[llength $setup]!=1 || ![fpga_checks::finite [get_property SLACK $setup]] ||
        [get_property SLACK $setup]<-0.5} {error "Large placed setup deficit; preserved for diagnosis before routing"}
    reset_impl_stage routing
    route_design
    route_design -finalize
    write_checkpoint [file join $::out before_physopt_routed.dcp]
    report_timing_summary -file [file join $::out before_physopt_timing.rpt]
    set needs_opt false
    foreach kind {max min} {
        set paths [get_timing_paths -quiet -delay_type $kind -max_paths 1]
        if {[llength $paths]!=1 || ![fpga_checks::finite [get_property SLACK $paths]]} {error "Invalid routed timing"}
        set slack [get_property SLACK $paths]
        if {$slack < -0.5} {error "Large routed $kind violation; no blind physical retry"}
        if {$slack < 0} {set needs_opt true}
    }
    if {$needs_opt} {
        reset_impl_stage bounded_postroute_optimization
        phys_opt_design -directive Explore
        if {![report_route_status -boolean_check ROUTED_FULLY]} {route_design}
    }
    write_checkpoint [file join $::out ara_dsa_vcu118_routed.dcp]
    reset_impl_stage strict_routed_gates
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        if {[report_route_status -boolean_check $check]!=$expected} {error "Route integrity: $check"}
    }
    dual_cdc_preflight [file join $::out routed_constraints] false
    fpga_run::require_timing [file join $::out routed_gate]
    report_bus_skew -file [file join $::out routed_gate bus_skew.rpt]
    set failures [fpga_checks::skew_failures [fpga_checks::read_report [file join $::out routed_gate bus_skew.rpt]] true]
    if {[llength $failures]} {error "Bus skew failed: $failures"}
    reset_impl_stage routed_ready_for_full_audit
    close_design
} message]} {puts stderr $::errorInfo; exit 1}
exit 0
