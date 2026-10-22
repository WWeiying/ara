# Actual Depth-stack root names are sealed by prepare, including collapsed names.
source [file join $env(DVE_COVERAGE_OUTPUT) combo-library.tcl]
proc qbsrefresh_row {scope stream stage} {
    global combo_root_names
    if {![info exists combo_root_names($scope)]} {error "Unbound aggregate report root"}
    qbsapp_root
    set token [qbsrefresh_select $scope]
    gui_covtable_setroot -id CoverageTable.1 $token
    gui_process_events -mstime 100
    set item [gui_list_get -id CoverageTable.1 -firstChild]
    if {$item eq "" || $item eq "0"} {error "Missing rooted row"}
    set path [gui_list_get -id CoverageTable.1 -path $item]
    set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $item]]
    set sibling [gui_list_get -id CoverageTable.1 -nextSibling $item]
    set basename [lindex [split $scope .] end]
    if {$path ne $name || ($name ne $basename && $name ne $combo_root_names($scope)) || ($sibling ne "" && $sibling ne "0")} {
        error "Nonunique root not bound to exact fullscope and actual displayed node"
    }
    array set metrics {}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq "Branch" || $label eq "Score"} {
            if {[info exists metrics($label)]} {error "Duplicate rooted metric"}
            set value [string trim [gui_list_get -id CoverageTable.1 -text $column $item]]
            if {$value eq ""} {set value NA}
            set metrics($label) $value
        }
    }
    if {![info exists metrics(Branch)] || ![info exists metrics(Score)]} {error "Missing rooted metrics"}
    opapp_csv $stream [list $stage $scope $token $item $path $name $metrics(Branch) $metrics(Score)]
}
set failed [catch {qbsapp_session} message]
if {$failed} {puts "COMBO_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists dbg_scopes]} {
    if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
}
if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
if {$failed || [llength $cleanup]} {puts "COMBO_FAILED $message cleanup=$cleanup"} else {puts COMBO_DONE_EXACT4328}
gui_exit -noprompt
