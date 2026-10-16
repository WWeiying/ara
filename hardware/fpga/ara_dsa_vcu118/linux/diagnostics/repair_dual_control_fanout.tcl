# Replicate only measured synchronous control startpoints, never CDC synchronizers.
proc control_stage {value} {
    set f [open [file join $::out stage.txt] w]; puts $f $value; close $f
    puts "CONTROL_REPAIR $value"; flush stdout
}
proc control_reports {label} {
    set dir [file join $::out $label]; file mkdir $dir
    report_timing_summary -report_unconstrained -file [file join $dir timing.rpt]
    report_timing -delay_type max -max_paths 100 -nworst 1 -file [file join $dir setup.rpt]
    report_timing -delay_type min -max_paths 30 -nworst 1 -file [file join $dir hold.rpt]
}
proc control_targets {} {
    set shared i_dram_wrapper/gen_ethernet.i_eth_shared_ddr
    set fabric i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/ddr_fabric/inst
    return [list \
        $shared/i_range/i_aw_spill_reg/spill_register_flushable_i/gen_spill_reg.b_full_q_reg \
        gen_ddr2.i_dram_wrapper_c2/i_ddr_r_cut/i_reg_r/spill_register_flushable_i/gen_spill_reg.b_full_q_reg \
        ${fabric}/s01_entry_pipeline/s01_mmu/inst/gen_endpoint.w_state_reg\[0\] \
        ${fabric}/s00_entry_pipeline/s00_mmu/inst/w_sreg/state_reg\[m_valid_i\] \
        $shared/i_mux/gen_mux.i_r_spill_reg/spill_register_flushable_i/gen_spill_reg.b_full_q_reg \
        ${shared}/i_isolate/i_axi_isolate/FSM_sequential_state_ar_q_reg\[0\]]
}
if {![info exists ::control_library_only]} {
  if {[catch {
    if {[llength $argv]!=4} {error "Expected checkpoint tools package output"}
    lassign $argv checkpoint tools package ::out
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    control_stage open_preserved_checkpoint
    open_checkpoint $checkpoint
    set ::dual_cdc_preflight_library_only true
    source [file join $tools dual_cdc_preflight.tcl]
    dual_cdc_preflight [file join $::out constraints_before] false
    control_stage verify_measured_control_startpoints
    set nets {}
    set f [open [file join $::out targets.tsv] w]
    puts $f "cell\tasync_reg\tdont_touch\tq_net\tdirect_loads"
    foreach name [control_targets] {
        set cell [get_cells -quiet -hier -filter "NAME == $name"]
        if {[llength $cell]!=1 || [get_property REF_NAME $cell] ni {FDCE FDRE FDPE FDSE}} {
            error "Measured control register missing/changed: $name"
        }
        foreach prop {ASYNC_REG DONT_TOUCH} {
            if {[get_property $prop $cell] in {1 true TRUE}} {error "Refuse protected control modification: $name / $prop"}
        }
        set q [get_pins -of_objects $cell -filter {REF_PIN_NAME == Q}]
        set net [get_nets -of_objects $q]
        if {[llength $net]!=1 || [get_property DONT_TOUCH $net] in {1 true TRUE}} {
            error "Missing/protected control net: $name"
        }
        set loads [get_pins -of_objects [get_nets -segments -of_objects $q] -filter {IS_LEAF && DIRECTION == IN}]
        puts $f "$name\t[get_property ASYNC_REG $cell]\t[get_property DONT_TOUCH $cell]\t[get_property NAME $net]\t[llength $loads]"
        lappend nets [get_property NAME $net]
    }
    close $f
    control_reports before
    control_stage targeted_control_replication
    # Explicit Q nets come from real failing path startpoints, not a global fanout rule.
    set expressions {}
    foreach name $nets {lappend expressions "NAME == $name"}
    set objects [get_nets -quiet -hier -filter [join $expressions { || }]]
    if {[llength $objects]!=[llength $nets]} {error "Control net resolution changed"}
    phys_opt_design -force_replication_on_nets $objects
    write_checkpoint [file join $::out replicated_placed.dcp]
    control_reports replicated
    control_stage place_replicated_controls
    phys_opt_design -placement_opt
    write_checkpoint [file join $::out controls_placed.dcp]
    control_reports after
    dual_cdc_preflight [file join $::out constraints_after] false
    report_bus_skew -file [file join $::out after bus_skew.rpt]
    control_stage completed_requires_comparison_no_route
    close_design
  } message]} {puts stderr $::errorInfo; control_stage failed; exit 1}
  exit 0
}
