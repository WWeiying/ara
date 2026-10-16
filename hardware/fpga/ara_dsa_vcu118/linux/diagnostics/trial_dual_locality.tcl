# One isolated placement experiment, never route or change the board.
proc locality_stage {name} {
    set f [open [file join $::trial_out stage.txt] w]
    puts $f $name
    close $f
    puts "LOCALITY_TRIAL $name"
    flush stdout
}
proc locality_trial {placed optimized tools out} {
    set ::trial_out $out
    foreach input [list $placed $optimized [file join $tools dual_cdc_preflight.tcl]] {
        if {![file isfile $input]} {error "Missing input: $input"}
    }
    set_param general.maxThreads 8
    locality_stage inspect_physical_anchors
    open_checkpoint $placed
    set plan [dual_locality::plan]
    close_design
    locality_stage open_original_optimized_netlist
    open_checkpoint $optimized
    set ::dual_cdc_preflight_library_only true
    source [file join $tools dual_cdc_preflight.tcl]
    unset ::dual_cdc_preflight_library_only
    locality_stage verify_unchanged_cdc_exceptions
    dual_cdc_preflight [file join $out serialized_constraints] false
    locality_stage apply_locality_only
    dual_locality::apply_plan $plan [file join $out assignments.tsv]
    report_utilization -slr -file [file join $out utilization_before.rpt]
    locality_stage placement_only
    # Match the original placer directive so the locality plan is the variable.
    place_design
    write_checkpoint [file join $out locality_placed.dcp]
    locality_stage report_placement_estimates
    report_timing_summary -delay_type min_max -max_paths 20 -report_unconstrained \
        -file [file join $out timing_summary.rpt]
    report_timing -delay_type max -max_paths 100 -nworst 1 -path_type full_clock_expanded \
        -file [file join $out setup_paths.rpt]
    report_utilization -slr -file [file join $out utilization_after.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    locality_stage complete_placement_trial_not_signoff
    close_design
}
source [file join [file dirname [info script]] dual_slr_locality.tcl]
if {![info exists ::locality_trial_library_only]} {
    if {[llength $argv]!=4} {error "Expected placed optimized tools output"}
    set ::trial_out [lindex $argv 3]
    if {[catch {locality_trial {*}$argv} message]} {
        puts stderr $::errorInfo
        locality_stage failed
        exit 1
    }
    exit 0
}
