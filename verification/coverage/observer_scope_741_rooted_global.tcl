# Exact scope-only successor of observer_scope_741_rooted.tcl.
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl
proc apply_reviewed_waivers {id} {
    global env observer_scopes p740_scopes p740_root_names
    if {$id ne "CoverageTable.1"} {error "Unexpected observer table"}
    source [file join $env(DVE_COVERAGE_OUTPUT) observer-plan.tcl]
    source [file join $env(DVE_COVERAGE_OUTPUT) root-selection.tcl]
    p740_save initial-empty.el
    p740_summary raw
    p740_root
    foreach path $observer_scopes {
        eval [list gui_exclude_items -id $id -annotation {Integration scope: observation-only, not an unreachability waiver} [list $path]]
    }
    gui_exclusion -id $id -recalculate
    if {![gui_cov_excl_review -isEmpty]} {error "Observer review unresolved"}
    p740_save observers.el
    p740_summary applied
    gui_exclusion -reset
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) observers.el]]
    gui_exclusion -id $id -recalculate
    if {![gui_cov_excl_review -isEmpty]} {error "Observer reload unresolved"}
    p740_save observers-reloaded.el
    p740_summary reloaded
    gui_exclusion -reset
    gui_exclusion -id $id -recalculate
    p740_save final-empty.el
    p740_summary reset
    puts OBSERVER_741_SAVE_RELOAD_RESET_DONE
}
