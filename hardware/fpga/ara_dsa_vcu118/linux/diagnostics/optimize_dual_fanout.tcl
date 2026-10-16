# One measured post-place optimization; no automatic routing or board access.
proc fanout_stage {name} {
    set f [open [file join $::fanout_out stage.txt] w]
    puts $f $name
    close $f
    puts "DUAL_FANOUT $name"
    flush stdout
}
proc optimize_dual_fanout {checkpoint tools out} {
    set ::fanout_out $out
    set_param general.maxThreads 8
    fanout_stage open_locality_placement
    open_checkpoint $checkpoint
    set ::dual_cdc_preflight_library_only true
    source [file join $tools dual_cdc_preflight.tcl]
    unset ::dual_cdc_preflight_library_only
    dual_cdc_preflight [file join $out constraints_before] false
    fanout_stage high_fanout_physical_optimization
    # Actual remaining worst path is reset recovery, 95.5% wire delay.
    # Let Vivado preserve logic semantics; do not manually clone synchronizers.
    phys_opt_design -directive AggressiveFanoutOpt
    write_checkpoint [file join $out fanout_placed.dcp]
    fanout_stage audit_after_optimization
    dual_cdc_preflight [file join $out constraints_after] false
    report_timing_summary -delay_type min_max -max_paths 20 -report_unconstrained \
        -file [file join $out timing_summary.rpt]
    report_timing -delay_type max -max_paths 100 -nworst 1 -path_type full_clock_expanded \
        -file [file join $out setup_paths.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    report_drc -file [file join $out drc.rpt]
    set paths [get_timing_paths -quiet -delay_type max -max_paths 1]
    if {[llength $paths]!=1} {error "Missing setup path"}
    set slack [get_property SLACK $paths]
    set f [open [file join $out setup_slack_ns.txt] w]
    puts $f $slack
    close $f
    if {$slack<0} {
        fanout_stage remaining_setup_violation_no_route
    } else {
        fanout_stage setup_nonnegative_pending_report_review_no_route
    }
    close_design
}
if {![info exists ::fanout_library_only]} {
    if {[llength $argv]!=3} {error "Expected checkpoint tools output"}
    set ::fanout_out [lindex $argv 2]
    if {[catch {optimize_dual_fanout {*}$argv} message]} {
        puts stderr $::errorInfo
        fanout_stage failed
        exit 1
    }
    exit 0
}
