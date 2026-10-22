# Tcl8.4. Only summary roots and native global EL exports; no singleton inventory.
proc compact777_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc compact777_summary {stage} {
    p740_root
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) modules_$stage.csv] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream {Stage Scope Token Handle GUIPath Name Score Line Toggle FSM Condition Branch}
    set failed [catch {foreach scope $::p740_scopes {p740_row $scope $stream $stage}} message]
    close $stream
    p740_root
    if {$failed} {error $message}
    puts "COMPACT777_SUMMARY $stage [llength $::p740_scopes]"
}
proc compact777_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    if {![gui_cov_excl_review -isEmpty]} {error "Rejected/unresolved native import"}
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc compact777_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) root-selection.tcl]]
    uplevel #0 [list source $::compact_root_helper]
    if {[llength $::p740_scopes] != 73} {error "Exact real root plus72 module summaries required"}
    file rename [file join $::env(DVE_COVERAGE_OUTPUT) summary.csv.partial] [file join $::env(DVE_COVERAGE_OUTPUT) raw.csv]
    compact777_save initial-empty.el
    compact777_summary raw
    compact777_load combined.el
    compact777_save applied.el
    compact777_summary applied
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    compact777_save reset-empty.el
    compact777_summary reset
    compact777_load applied.el
    compact777_save reloaded.el
    compact777_summary reloaded
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    compact777_save final-empty.el
    compact777_summary final
}
proc apply_reviewed_waivers {id} {
    if {$id ne "CoverageTable.1"} {error "Unexpected table"}
    set failed [catch {compact777_session} message]
    set cleanup_failed [catch {
        gui_exclusion -reset
        gui_exclusion -id CoverageTable.1 -recalculate
        gui_process_events -mstime 100
        compact777_save cleanup-empty.el
    } cleanup]
    if {$failed} {puts "COMPACT777_FAILED: $message"; error $message}
    if {$cleanup_failed} {puts "COMPACT777_FAILED: $cleanup"; error $cleanup}
    puts COMPACT777_FIVE_PHASE_DONE
}
