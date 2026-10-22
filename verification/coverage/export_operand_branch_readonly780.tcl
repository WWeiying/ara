# Tcl8.4. Discovery only: no selection, exclusion, reset, save or load APIs.
proc obr_need {ok why} {if {!$ok} {error $why}}
proc obr_walk {scope item depth stream columns} {
    global obr_seen obr_count
    obr_need [expr {$depth < 16}] "Detail nesting bound"
    while {$item ne "" && $item ne "0"} {
        obr_need [expr {![info exists obr_seen($item)] && $obr_count < 2048}] "Native cycle/count bound"
        set obr_seen($item) 1
        incr obr_count
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set cells {}
        foreach c $columns {lappend cells [gui_list_get -id CovDetail.1 -text $c $item]}
        puts $stream [list row $scope $item $path $meta $depth $cells]
        obr_walk $scope [gui_list_get -id CovDetail.1 -firstChild $item] [expr {$depth+1}] $stream $columns
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc obr_snapshot {scope stream} {
    global obr_seen obr_count
    gui_list_action -id CoverageTable.1 -column Branch $scope
    obr_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Wrong native detail type"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set columns {}; set labels {}
    for {set c 0} {$c < 64} {incr c} {
        if {[catch {gui_list_get_property -id CovDetail.1 -column $c} label]} {break}
        if {[string trim $label] ne ""} {lappend columns $c; lappend labels $label}
    }
    obr_need [expr {[llength $columns] > 0}] "Native columns unavailable"
    puts $stream [list columns $scope $columns $labels]
    catch {unset obr_seen}; array set obr_seen {}; set obr_count 0
    obr_walk $scope [gui_list_get -id CovDetail.1 -firstChild] 0 $stream $columns
    obr_need [expr {$obr_count > 0}] "Empty detail inventory"
    puts $stream [list scope_complete $scope $obr_count]
    flush $stream
}
proc obr_session {} {
    global env obr_design obr_testdirs obr_tests obr_scopes
    uplevel #0 [list source $env(OPERAND_BRANCH_READONLY_SELECTION)]
    obr_need [expr {[llength $obr_scopes] == 2 && [llength $obr_tests] == 780}] "Exact approved discovery population/scope count"
    gui_open_cov -hier $obr_design -testdir $obr_testdirs -test $obr_tests -merge Operand780ReadOnlyBranchMapping
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set stream [open [file join $env(OPERAND_BRANCH_READONLY_OUTPUT) native-branch.tcllist] {WRONLY CREAT EXCL}]
    set failed [catch {foreach scope $obr_scopes {obr_snapshot $scope $stream}} message]
    close $stream
    if {$failed} {error $message}
    puts OPERAND_BRANCH_READONLY_COMPLETE_NOT_QUALIFICATION
}
# Managed host owns the process lifetime; discovery does not invoke GUI exit.
if {![info exists obr_library_only]} {obr_session}
