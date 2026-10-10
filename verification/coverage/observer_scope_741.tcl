# Hook into the frozen raw exporter; Tcl 8.4-compatible argument construction.
proc observer_summary {id name} {
    global env seen row_count
    set columns {}
    set header {Name Depth}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id $id -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        lappend columns $column
        lappend header $label
    }
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) $name] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream $header
    array unset seen
    array set seen {}
    set row_count 0
    set failed [catch {export_rows $stream $id "" 0 $columns} message]
    close $stream
    if {$failed || $row_count == 0} {error "Observer summary failed: $message"}
}
proc apply_reviewed_waivers {id} {
    global env observer_scopes
    source [file join $env(DVE_COVERAGE_OUTPUT) observer-plan.tcl]
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]]
    foreach path $observer_scopes {
        eval [list gui_exclude_items -id $id -annotation {Integration scope: observation-only, not an unreachability waiver} [list $path]]
    }
    gui_exclusion -id $id -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Observer exclusions need review"}
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) observers.el]]
    observer_summary $id summary_scoped.csv
    gui_exclusion -reset
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) observers.el]]
    gui_exclusion -id $id -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Reloaded observers need review"}
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) observers-reloaded.el]]
    observer_summary $id summary_reloaded.csv
    gui_exclusion -reset
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) final-empty.el]]
    observer_summary $id summary_reset.csv
    puts OBSERVER_741_SAVE_RELOAD_RESET_DONE
}
