# Reuse sealed repaired synthesis, with an isolated corrected constraint set.
proc dual_cdc_stage {out stage} {
    set f [open [file join $out stage.txt] w]
    puts $f $stage
    close $f
    puts "DUAL_CDC_STAGE $stage"
    flush stdout
}
if {[catch {
    if {[llength $argv]!=4} {error "Expected bundle tools output run_suffix"}
    lassign $argv bundle tools out suffix
    if {![regexp {^[a-f0-9]{12}$} $suffix]} {error "Invalid suffix"}
    set package [file join $bundle package]
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    source [file join $package scripts common.tcl]
    source [file join $package scripts run_support.tcl]
    set ::rebuild_test_mode true
    source [file join $tools rebuild_mainrtl.tcl]
    set ::dual_cdc_preflight_library_only true
    source [file join $tools dual_cdc_preflight.tcl]
    unset ::dual_cdc_preflight_library_only
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    set_msg_config -id {Common 17-1548} -new_severity ERROR
    set_msg_config -id {Board 49-67} -new_severity ERROR
    dual_cdc_stage $out reuse_verified_synthesis
    open_package_project
    fpga_run::check_ips
    fpga_run::reusable synth_903503b5ace4 {*synth_design Complete*} ara_dsa_vcu118.dcp
    set cs constrs_cdc_$suffix
    if {[llength [get_filesets -quiet $cs]]} {error "Constraint set already exists"}
    create_fileset -constrset $cs
    set replaced 0
    set sources [get_files -quiet -of_objects [get_filesets constrs_1]]
    if {[llength $sources]!=6} {error "Unexpected archived constraint inventory"}
    foreach old $sources {
        set path [get_property NAME $old]
        if {[file tail $path] eq "cdc.xdc"} {
            set path [file join $tools cdc.xdc]
            incr replaced
        }
        add_files -fileset $cs -norecurse $path
        set new [get_files -quiet -of_objects [get_filesets $cs] $path]
        if {[llength $new]!=1} {error "Missing copied constraint: $path"}
        foreach key {FILE_TYPE USED_IN_SYNTHESIS USED_IN_IMPLEMENTATION PROCESSING_ORDER} {
            set_property $key [get_property $key $old] $new
        }
    }
    if {$replaced!=1} {error "CDC overlay was not applied exactly once"}
    set run_name impl_cdc_$suffix
    set run [fpga_run::clone_run impl_1 $run_name synth_903503b5ace4]
    set_property CONSTRSET $cs $run
    set_property STEPS.OPT_DESIGN.TCL.PRE [file join $tools dual_cdc_preflight.tcl] $run
    current_run -implementation $run
    dual_cdc_stage $out link_and_optimize_corrected_constraints
    launch_runs $run_name -jobs 1 -dir $out -to_step opt_design
    set optimized [rebuild_opt_complete $run_name [file join $out $run_name]]
    close_project
    dual_cdc_stage $out check_serialized_constraints
    open_checkpoint $optimized
    dual_cdc_preflight [file join $out serialized_constraints] false
    require_no_multiple_drivers [file join $out preflight]
    require_no_combinational_loops [file join $out preflight]
    # The single-DDR reference matched only 78.07%, below Vivado's 80% threshold.
    # The previous dual-DDR route was optimized with missing constraints. Do not
    # reuse that invalid physical solution or claim incremental placement.
    dual_cdc_stage $out placement
    place_design
    write_checkpoint [file join $out placed.dcp]
    dual_cdc_stage $out check_placed_setup
    report_timing_summary -file [file join $out placed_timing.rpt]
    report_timing -delay_type max -max_paths 50 -nworst 1 \
        -file [file join $out placed_setup_paths.rpt]
    set placed_setup [get_timing_paths -quiet -delay_type max -max_paths 1]
    if {[llength $placed_setup]!=1} {error "Missing placed setup path"}
    # Placement hold estimates may be repaired during routing. A large setup
    # deficit instead needs endpoint/constraint diagnosis before an expensive run.
    if {[get_property SLACK $placed_setup] < -0.5} {
        error "Large placed setup violation requires diagnosis; placement preserved, routing not started"
    }
    dual_cdc_stage $out routing
    route_design
    dual_cdc_stage $out finalize_route
    route_design -finalize
    write_checkpoint [file join $out before_physopt_routed.dcp]
    report_timing_summary -file [file join $out before_physopt_timing.rpt]
    set worst [get_timing_paths -quiet -delay_type max -max_paths 1]
    set hold [get_timing_paths -quiet -delay_type min -max_paths 1]
    if {[llength $worst]!=1 || [llength $hold]!=1} {error "Missing timing paths"}
    set setup_slack [get_property SLACK $worst]
    set hold_slack [get_property SLACK $hold]
    if {$setup_slack<0 || $hold_slack<0} {
        if {$setup_slack < -0.5 || $hold_slack < -0.5} {
            error "Large routed violation requires diagnosis; no blind multi-hour phys_opt retry"
        }
        dual_cdc_stage $out bounded_physical_optimization
        phys_opt_design -directive Explore
        if {![report_route_status -boolean_check ROUTED_FULLY]} {route_design}
    }
    write_checkpoint [file join $out ara_dsa_vcu118_routed.dcp]
    dual_cdc_stage $out strict_routed_gates
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        if {[report_route_status -boolean_check $check]!=$expected} {error "Route integrity: $check"}
    }
    fpga_run::require_timing [file join $out routed_gate]
    report_bus_skew -file [file join $out routed_gate bus_skew.rpt]
    set failures [fpga_checks::skew_failures [fpga_checks::read_report [file join $out routed_gate bus_skew.rpt]] true]
    if {[llength $failures]} {error "Bus skew failed: $failures"}
    dual_cdc_stage $out routed_ready_for_full_audit
    close_design
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
