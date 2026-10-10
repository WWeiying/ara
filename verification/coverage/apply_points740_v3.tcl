# Tcl8.4: mature qbsapp_root/summary refresh; point-only import, no scope exclusions.
proc p740_save {name} {
    global env
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) $name]]
}

proc p740_csv {id name} {
    global env seen row_count
    gui_covtable_show -id $id -show {Design Hierarchy} -cumulative 1
    gui_covtable_setroot -id $id ara_tb
    gui_list_expand -id $id -all {<root>}
    gui_cov_show_value -switch false
    gui_process_events -mstime 100
    set first [gui_list_get -id $id -firstChild]
    if {$first eq "" || $first eq "0" || [gui_list_get -id $id -path $first] ne "ara_tb"} {
        error "Full-root GUI contract differs"
    }
    gui_exclusion -id $id -recalculate
    gui_process_events -mstime 100
    set columns {}
    set header {Name Depth}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id $id -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        lappend columns $column
        lappend header $label
    }
    if {[llength $columns] == 0} {error "No coverage columns"}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) $name] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream $header
    catch {array unset seen}
    array set seen {}
    set row_count 0
    set failed [catch {export_rows $stream $id "" 0 $columns} message]
    close $stream
    if {$failed} {error $message}
    if {$row_count == 0} {error "Empty full hierarchy"}
}

proc p740_session {id} {
    global env
    file rename [file join $env(DVE_COVERAGE_OUTPUT) summary.csv.partial] [file join $env(DVE_COVERAGE_OUTPUT) raw.csv]
    p740_save initial-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) points.el]]
    if {![gui_cov_excl_review -isEmpty]} {error "Rejected/unresolved point import"}
    gui_exclusion -id $id -recalculate
    p740_save applied.el
    p740_csv $id applied.csv
    gui_exclusion -reset
    p740_save reset-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) applied.el]]
    if {![gui_cov_excl_review -isEmpty]} {error "Rejected/unresolved point reload"}
    gui_exclusion -id $id -recalculate
    p740_save reloaded.el
    p740_csv $id reloaded.csv
    gui_exclusion -reset
    gui_exclusion -id $id -recalculate
    p740_save final-empty.el
    p740_csv $id reset.csv
}

proc apply_reviewed_waivers {id} {
    set failed [catch {p740_session $id} message]
    set cleanup_failed [catch {gui_exclusion -reset; p740_save cleanup-empty.el} cleanup]
    if {$failed} {error $message}
    if {$cleanup_failed} {error $cleanup}
    puts POINT740_APPLIED_RELOADED_RESET_DONE
}

