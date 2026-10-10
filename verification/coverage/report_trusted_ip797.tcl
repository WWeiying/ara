# Exact execution-IP scopes; retain inherited point exclusions outside them.
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_global777_compact.tcl
proc compact777_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) root-selection.tcl]]
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) trusted-scopes.tcl]]
    uplevel #0 [list source $::compact_root_helper]
    if {[llength $::trusted_scopes] != 577 || [llength $::p740_scopes] != 73} {error "Approved scope count differs"}
    file rename [file join $::env(DVE_COVERAGE_OUTPUT) summary.csv.partial] [file join $::env(DVE_COVERAGE_OUTPUT) raw.csv]
    compact777_save initial-empty.el
    compact777_summary raw
    compact777_load combined.el
    p740_root
    foreach scope $::trusted_scopes {
        gui_exclude_items -id CoverageTable.1 -annotation {Trusted execution IP integration scope; not unreachability or exhaustive verification} [list $scope]
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    if {![gui_cov_excl_review -isEmpty]} {error "Rejected trusted IP scope"}
    compact777_save applied.el
    compact777_summary applied
    gui_exclusion -reset
    compact777_save reset-empty.el
    compact777_summary reset
    compact777_load applied.el
    compact777_save reloaded.el
    compact777_summary reloaded
    gui_exclusion -reset
    compact777_save final-empty.el
    compact777_summary final
    puts TRUSTED797_FIVE_PHASE_DONE
}
