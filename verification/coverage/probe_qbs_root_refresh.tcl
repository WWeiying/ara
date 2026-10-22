# Tcl 8.4. No update API; exact singleton full token followed by local root binding.
set qbsapp_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_qbs_historical.tcl}
rename qbsapp_summary qbsrefresh_full_summary
proc qbsrefresh_tokens {raw} {
    if {[llength $raw] == 0} {return {}}
    if {[llength $raw] != 1} {error "Multiple selection groups"}
    set group [lindex $raw 0]
    if {[llength $group] > 1} {error "Multiple selection tokens"}
    if {[llength $group] == 0} {return {}}
    return [list [lindex $group 0]]
}
proc qbsrefresh_select {scope} {
    set clear [qbsrefresh_tokens [gui_list_get_selected -id CoverageTable.1 -flat]]
    if {[llength $clear]} {gui_list_select -id CoverageTable.1 -unselect $clear}
    gui_list_select -id CoverageTable.1 -select [list $scope]
    set tokens [qbsrefresh_tokens [gui_list_get_selected -id CoverageTable.1 -flat]]
    if {[llength $tokens] != 1 || [lindex $tokens 0] ne $scope} {error "Requested full token not selected"}
    return [lindex $tokens 0]
}
proc qbsrefresh_row {scope stream stage} {
    qbsapp_root
    set token [qbsrefresh_select $scope]
    gui_covtable_setroot -id CoverageTable.1 $token
    gui_process_events -mstime 100
    set item [gui_list_get -id CoverageTable.1 -firstChild]
    if {$item eq "" || $item eq "0"} {error "Missing rooted row"}
    set path [gui_list_get -id CoverageTable.1 -path $item]
    set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $item]]
    set sibling [gui_list_get -id CoverageTable.1 -nextSibling $item]
    set expected [lindex [split $scope .] end]
    if {$path ne $expected || $name ne $expected || ($sibling ne "" && $sibling ne "0")} {
        error "Nonunique LOCAL root binding for $scope"
    }
    array set metrics {}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq "Branch" || $label eq "Score"} {
            if {[info exists metrics($label)]} {error "Duplicate rooted metric"}
            set metrics($label) [string trim [gui_list_get -id CoverageTable.1 -text $column $item]]
        }
    }
    if {![info exists metrics(Branch)] || ![info exists metrics(Score)]} {error "Missing rooted metrics"}
    opapp_csv $stream [list $stage $scope $token $item $path $name $metrics(Branch) $metrics(Score)]
}
proc qbsapp_summary {stage} {
    global env qbsrefresh_scopes
    qbsrefresh_full_summary $stage
    source [file join $env(DVE_COVERAGE_OUTPUT) root-selection.tcl]
    set mode a
    if {$stage eq "raw"} {set mode w}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) rooted-metrics.csv] $mode]
    fconfigure $stream -encoding utf-8 -translation lf
    if {$mode eq "w"} {opapp_csv $stream {Stage RequestedScope Token Handle GUIPath Name Branch Score}}
    set failed [catch {
        foreach scope $qbsrefresh_scopes {qbsrefresh_row $scope $stream $stage}
    } message]
    close $stream
    qbsapp_root
    if {$failed} {error $message}
}
set failed [catch {qbsapp_session} message]
if {$failed} {puts "QBSAPP_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists dbg_scopes]} {
    if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
}
if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
if {$failed || [llength $cleanup]} {puts "QBSAPP_FAILED $message cleanup=$cleanup"} else {puts QBSAPP_DONE_EXACT448}
gui_exit -noprompt
