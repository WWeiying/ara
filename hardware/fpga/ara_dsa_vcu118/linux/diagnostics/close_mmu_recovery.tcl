# One measured post-route recovery-tail experiment; never relax constraints.
proc stage {out name} {
    set f [open [file join $out stage.txt] w]
    puts $f $name
    close $f
    puts "RECOVERY_STAGE $name"
    flush stdout
}
if {[catch {
    if {[llength $argv] != 3} {error "Expected checkpoint package output"}
    lassign $argv checkpoint package out
    source [file join $package scripts run_support.tcl]
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    if {[llength [get_board_parts -quiet xilinx.com:vcu118:part0:2.4]] != 1} {
        error "Missing frozen board definition"
    }
    set_msg_config -id {Board 49-67} -new_severity ERROR
    set_msg_config -id {Constraints 18-638} -new_severity ERROR
    stage $out opening
    open_checkpoint $checkpoint
    if {[llength [get_cells -quiet -hierarchical -filter {IS_BLACKBOX == 1}]]} {
        error "Unresolved blackboxes in routed design"
    }
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        if {[report_route_status -boolean_check $check] != $expected} {error "Bad route: $check"}
    }
    stage $out verifying_recovery_tail
    report_timing_summary -file [file join $out before_timing.rpt]
    set paths [get_timing_paths -quiet -delay_type max -slack_lesser_than 0 -max_paths 200 -nworst 1]
    if {[llength $paths] != 2} {error "Expected exactly two violating endpoints"}
    foreach path $paths {
        set src [get_property STARTPOINT_PIN $path]
        set dst [get_property ENDPOINT_PIN $path]
        set slack [get_property SLACK $path]
        if {$src ne {i_dram_wrapper/i_ui_rstgen/i_rstgen_bypass/synch_regs_q_reg[3]/C} ||
            ![string match {i_dram_wrapper/gen_cdc.i_axi_cdc_mig/*/CLR} $dst] ||
            $slack < -0.02 || $slack >= 0} {
            error "Unreviewed path: $src -> $dst slack=$slack"
        }
        puts "REVIEWED_RECOVERY $src -> $dst slack=$slack"
    }
    report_timing -delay_type max -slack_lesser_than 0 -max_paths 200 -nworst 1 -file [file join $out recovery_before.rpt]
    stage $out physical_optimization
    phys_opt_design -directive Explore
    if {![report_route_status -boolean_check ROUTED_FULLY]} {
        stage $out repair_routing
        route_design
    }
    # Retain the experimental result even when strict acceptance fails.
    write_checkpoint [file join $out candidate_routed.dcp]
    stage $out strict_gate
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        if {[report_route_status -boolean_check $check] != $expected} {error "Bad route: $check"}
    }
    report_route_status -file [file join $out route_status.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    fpga_run::require_timing $out
    stage $out timing_passed_needs_full_audit
    close_design
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
