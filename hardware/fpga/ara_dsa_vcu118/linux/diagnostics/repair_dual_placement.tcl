# One discriminating placement-only pass from the preserved placed design.
proc repair_stage {value} {
    set f [open [file join $::out stage.txt] w]; puts $f $value; close $f
    puts "PLACEMENT_REPAIR $value"; flush stdout
}
proc repair_measure {label} {
    set dir [file join $::out $label]
    file mkdir $dir
    report_timing_summary -report_unconstrained -file [file join $dir timing.rpt]
    report_timing -delay_type max -max_paths 100 -nworst 1 -file [file join $dir setup.rpt]
    report_timing -delay_type min -max_paths 50 -nworst 1 -file [file join $dir hold.rpt]
    set f [open [file join $dir failing_setup.tsv] w]
    puts $f "slack\tstartpoint\tendpoint"
    set paths [get_timing_paths -quiet -delay_type max -slack_lesser_than 0 -max_paths 20000 -nworst 1]
    foreach path $paths {
        puts $f "[get_property SLACK $path]\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
    }
    close $f
    if {[llength $paths]>=20000} {error "Setup inventory truncated; inspect reports"}
}
if {[catch {
    if {[llength $argv]!=3} {error "Expected checkpoint tools output"}
    lassign $argv checkpoint tools ::out
    set_param general.maxThreads 8
    repair_stage open_preserved_checkpoint
    open_checkpoint $checkpoint
    set ::dual_cdc_preflight_library_only true
    source [file join $tools dual_cdc_preflight.tcl]
    dual_cdc_preflight [file join $::out constraints_before] false
    repair_stage measure_before
    repair_measure before
    # Hypothesis: critical control cells are too far from their UI-clock sinks.
    # Change placement only; do not relax constraints or alter pipeline latency.
    repair_stage critical_path_replacement
    phys_opt_design -placement_opt
    write_checkpoint [file join $::out repaired_placed.dcp]
    repair_stage measure_after
    repair_measure after
    dual_cdc_preflight [file join $::out constraints_after] false
    report_bus_skew -file [file join $::out after bus_skew.rpt]
    report_drc -file [file join $::out after drc.rpt]
    repair_stage completed_requires_timing_comparison_no_route
    close_design
} message]} {puts stderr $::errorInfo; repair_stage failed; exit 1}
exit 0
