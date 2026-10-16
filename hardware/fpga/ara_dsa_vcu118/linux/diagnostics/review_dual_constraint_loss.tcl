# Diagnose one frozen routed DCP in memory. No implementation or hardware access.
proc review_stage {out name} {
    set f [open [file join $out stage.txt] w]
    puts $f $name
    close $f
    puts "CONSTRAINT_REVIEW $name"
    flush stdout
}
if {[catch {
    if {[llength $argv] != 4} {error "Expected checkpoint package candidate_cdc output"}
    lassign $argv checkpoint package candidate out
    if {[file exists $out]} {error "Review output already exists"}
    file mkdir $out
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    set_msg_config -id {Board 49-67} -new_severity ERROR
    review_stage $out opening
    open_checkpoint $checkpoint
    set f [open [file join $out context.txt] w]
    foreach fs [get_filesets -quiet sources_1] {
        puts $f "FILESET=$fs MODE=[get_property DESIGN_MODE $fs] DEFINES=[get_property verilog_define $fs]"
    }
    puts $f "SECOND_DDR=[get_pins -quiet gen_ddr2.i_dram_wrapper_c2/soc_clk_i]"
    puts $f "HUB_CLOCK=[get_clocks -quiet -of_objects [get_pins dbg_hub/clk]]"
    puts $f "VIO_CLOCK=[get_clocks -quiet -of_objects [get_pins i_vio/clk]]"
    close $f
    write_xdc -exclude_physical [file join $out before.xdc]
    set ::fpga_profile dual_ddr_ethernet
    set ::ara_cdc_library_only true
    source $candidate
    unset ::ara_cdc_library_only
    review_stage $out restoring_missing_timing_constraints_only
    # Debug-hub connection must be fixed before opt_design, not in this review.
    ara_cdc::apply false
    write_xdc -exclude_physical [file join $out after.xdc]
    review_stage $out measuring
    report_timing_summary -report_unconstrained -file [file join $out after_timing.rpt]
    report_timing -delay_type max -max_paths 30 -nworst 1 -slack_lesser_than 0 -file [file join $out setup.rpt]
    report_timing -delay_type min -max_paths 30 -nworst 1 -slack_lesser_than 0 -file [file join $out hold.rpt]
    report_exceptions -coverage -file [file join $out coverage.rpt]
    report_exceptions -ignored -file [file join $out ignored.rpt]
    report_bus_skew -file [file join $out skew.rpt]
    review_stage $out reviewed_not_timing_or_hardware_acceptance
    close_design
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
