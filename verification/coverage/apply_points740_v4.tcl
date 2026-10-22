# Tcl8.4. Eleven exact rooted summaries; full raw exporter remains untouched.
proc p740_save {name} {
    global env
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) $name]]
}
proc p740_root {} {
    gui_covtable_show -id CoverageTable.1 -show {Design Hierarchy} -cumulative 1
    gui_covtable_setroot -id CoverageTable.1 ara_tb
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_cov_show_value -switch false
    gui_process_events -mstime 100
    set first [gui_list_get -id CoverageTable.1 -firstChild]
    if {$first eq "" || $first eq "0" || [gui_list_get -id CoverageTable.1 -path $first] ne "ara_tb"} {
        error "Full-root GUI contract differs"
    }
}
proc p740_tokens {raw} {
    if {[llength $raw] == 0} {return {}}
    if {[llength $raw] != 1} {error "Multiple selection groups"}
    set group [lindex $raw 0]
    if {[llength $group] > 1} {error "Multiple selection tokens"}
    if {[llength $group] == 0} {return {}}
    set token [lindex $group 0]
    if {$token eq ""} {return {}}
    return [list $token]
}
proc p740_select {scope} {
    set clear [p740_tokens [gui_list_get_selected -id CoverageTable.1 -flat]]
    if {[llength $clear]} {gui_list_select -id CoverageTable.1 -unselect $clear}
    gui_list_select -id CoverageTable.1 -select [list $scope]
    set tokens [p740_tokens [gui_list_get_selected -id CoverageTable.1 -flat]]
    if {[llength $tokens] != 1 || [lindex $tokens 0] ne $scope} {error "Requested full token not selected"}
    return [lindex $tokens 0]
}
proc p740_row {scope stream stage} {
    global p740_root_names
    if {![info exists p740_root_names($scope)]} {error "Unbound requested root"}
    p740_root
    set token [p740_select $scope]
    gui_covtable_setroot -id CoverageTable.1 $token
    gui_process_events -mstime 100
    set item [gui_list_get -id CoverageTable.1 -firstChild]
    if {$item eq "" || $item eq "0"} {error "Missing rooted row"}
    set path [gui_list_get -id CoverageTable.1 -path $item]
    set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $item]]
    set sibling [gui_list_get -id CoverageTable.1 -nextSibling $item]
    set basename [lindex [split $scope .] end]
    if {$path ne $name || ($name ne $basename && $name ne $p740_root_names($scope)) || ($sibling ne "" && $sibling ne "0")} {
        error "Nonunique root not bound to exact fullscope/displayed node"
    }
    array set metrics {}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} label]} {break}
        set label [string trim $label]
        if {[lsearch -exact {Score Line Toggle FSM Condition Branch} $label] >= 0} {
            if {[info exists metrics($label)]} {error "Duplicate rooted metric"}
            set value [string trim [gui_list_get -id CoverageTable.1 -text $column $item]]
            if {$value eq ""} {set value NA}
            set metrics($label) $value
        }
    }
    set values [list $stage $scope $token $item $path $name]
    foreach metric {Score Line Toggle FSM Condition Branch} {
        if {![info exists metrics($metric)]} {error "Missing rooted metric $metric"}
        lappend values $metrics($metric)
    }
    csv_row $stream $values
}
proc p740_summary {stage} {
    global env p740_scopes p740_root_names
    p740_root
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) rooted_$stage.csv] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream {Stage Scope Token Handle GUIPath Name Score Line Toggle FSM Condition Branch}
    set failed [catch {foreach scope $p740_scopes {p740_row $scope $stream $stage}} message]
    close $stream
    p740_root
    if {$failed} {error $message}
    puts "POINT740_ROOTED_SUMMARY $stage [llength $p740_scopes]"
}
proc p740_session {} {
    global env p740_scopes p740_root_names
    source [file join $env(DVE_COVERAGE_OUTPUT) root-selection.tcl]
    if {[llength $p740_scopes] != 11} {error "Exact eleven roots required"}
    file rename [file join $env(DVE_COVERAGE_OUTPUT) summary.csv.partial] [file join $env(DVE_COVERAGE_OUTPUT) raw.csv]
    p740_save initial-empty.el
    p740_summary raw
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) points.el]]
    if {![gui_cov_excl_review -isEmpty]} {error "Rejected/unresolved point import"}
    gui_exclusion -id CoverageTable.1 -recalculate
    p740_save applied.el
    p740_summary applied
    gui_exclusion -reset
    p740_save reset-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) applied.el]]
    if {![gui_cov_excl_review -isEmpty]} {error "Rejected/unresolved point reload"}
    gui_exclusion -id CoverageTable.1 -recalculate
    p740_save reloaded.el
    p740_summary reloaded
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    p740_save final-empty.el
    p740_summary reset
}
proc apply_reviewed_waivers {id} {
    if {$id ne "CoverageTable.1"} {error "Unexpected summary table"}
    set failed [catch {p740_session} message]
    set cleanup_failed [catch {gui_exclusion -reset; p740_save cleanup-empty.el} cleanup]
    if {$failed} {error $message}
    if {$cleanup_failed} {error $cleanup}
    file copy [file join $::env(DVE_COVERAGE_OUTPUT) rooted_applied.csv] [file join $::env(DVE_COVERAGE_OUTPUT) summary_waived.csv]
    puts POINT740_APPLIED_RELOADED_RESET_DONE
}
