# Exactly one fresh placement; no incremental import from the failed trials.
proc floor_place_stage {value} {
    set f [open [file join $::out stage.txt] w]; puts $f $value; close $f
    puts "FLOOR_PLACE $value"; flush stdout
}
proc floor_place_reports {label} {
    set dir [file join $::out $label]; file mkdir $dir
    report_timing_summary -report_unconstrained -file [file join $dir timing.rpt]
    report_timing -delay_type max -max_paths 100 -nworst 1 -path_type full_clock_expanded -file [file join $dir setup.rpt]
    report_timing -delay_type min -max_paths 30 -nworst 1 -path_type full_clock_expanded -file [file join $dir hold.rpt]
    report_clock_utilization -file [file join $dir clocks.rpt]
    report_utilization -slr -file [file join $dir slr.rpt]
    report_design_analysis -congestion -file [file join $dir congestion.rpt]
}
if {[catch {
    if {[llength $argv]!=4} {error "Expected optimized_checkpoint tools package output"}
    lassign $argv checkpoint tools package ::out
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    source [file join $::out dual_floorplan.tcl]
    set ::dual_cdc_preflight_library_only true
    source [file join $tools dual_cdc_preflight.tcl]
    set ::dual_reset_library_only true
    source [file join $tools check_dual_reset_netlist.tcl]
    source [file join $tools dual_slr_locality.tcl]
    floor_place_stage open_clean_optimized_netlist
    open_checkpoint $checkpoint
    check_dual_reset_netlist $::out
    dual_cdc_preflight [file join $::out constraints_before] false
    # Preserve the known PHY and DDR SLR guidelines without loading a placed DCP.
    set soft {}
    set phy i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/mac/inst/pcs_pma/inst/pcs_pma_block_i
    lappend soft [list $phy SLR1]
    foreach wrapper {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} slr {SLR2 SLR0} {
        foreach block {gen_cdc.i_axi_cdc_mig i_ddr_r_cut i_ui_rstgen i_ui_por} {
            lappend soft [list $wrapper/$block $slr]
        }
    }
    lappend soft [list i_dram_wrapper/gen_ethernet.i_eth_shared_ddr SLR2]
    dual_locality::apply_plan $soft [file join $::out soft_slr.tsv]
    floor_place_stage apply_reviewed_physical_regions
    dual_floor::apply [file join $::out floorplan]
    write_checkpoint [file join $::out floorplanned_opt.dcp]
    floor_place_stage global_placement_attempt_1
    place_design
    write_checkpoint [file join $::out placed.dcp]
    floor_place_reports placed
    # Same one-pass fanout optimization as the original placement baseline.
    floor_place_stage standard_physical_optimization
    phys_opt_design -directive AggressiveFanoutOpt
    write_checkpoint [file join $::out physical_placed.dcp]
    floor_place_reports physical
    dual_cdc_preflight [file join $::out constraints_after] false
    report_bus_skew -file [file join $::out physical bus_skew.rpt]
    report_drc -file [file join $::out physical drc.rpt]
    # Keep attempt two manual and evidence-driven, never automatically retry.
    floor_place_stage placed_requires_whole_design_review_no_route
    close_design
} message]} {puts stderr $::errorInfo; floor_place_stage failed; exit 1}
exit 0
