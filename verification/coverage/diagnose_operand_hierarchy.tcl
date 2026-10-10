# Independent UI-only probe. No new exclusion selection or corpus report.
proc oph_write {stage scope token} {
    global env
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) observations.tsv] a]
    for {set col 5} {$col < 32} {incr col} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $col} label]} {break}
        if {[string trim $label] eq ""} {continue}
        set value [gui_list_get -id CoverageTable.1 -text $col $token]
        foreach field [list $stage $scope $token $label $value] {
            if {[regexp {[\t\r\n]} $field]} {close $stream; error "Non TSV observation"}
        }
        puts $stream "$stage\t$scope\t$token\t$label\t$value"
    }
    close $stream
}
proc oph_find {parent scope depth} {
    if {$depth > 32} {error "Probe traversal depth exceeded"}
    if {$parent eq ""} {set item [gui_list_get -id CoverageTable.1 -firstChild]} else {
        set item [gui_list_get -id CoverageTable.1 -firstChild $parent]
    }
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CoverageTable.1 -path $item]
        if {$path eq $scope} {return $item}
        if {[string first "$path." $scope] == 0} {
            gui_list_expand -id CoverageTable.1 $path
            gui_process_events
            set found [oph_find $item $scope [expr {$depth+1}]]
            if {$found ne ""} {return $found}
        }
        set item [gui_list_get -id CoverageTable.1 -nextSibling $item]
    }
    return ""
}
proc oph_observe {stage scope} {
    set item [oph_find "" $scope 0]
    if {$item eq ""} {error "Scope not found: $scope"}
    oph_write $stage $scope $item
}
proc oph_fullroot {} {
    gui_covtable_show -id CoverageTable.1 -show {Design Hierarchy} -cumulative 1
    gui_covtable_setroot -id CoverageTable.1 ara_tb
    gui_process_events
}
proc oph_session {} {
    global env opapp_library_only op1144_design op1144_test op1144_keys op1144_targets
    global opapp_databases opapp_tests opapp_native op1144_scopes
    set opapp_library_only 1
    source $env(OPH_APP_HOOK)
    opapp_load
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    foreach command {gui_covtable_setroot gui_covtable_show gui_list_select gui_list_get_selected gui_list_get gui_cov_show_value gui_process_events gui_exclusion} {
        puts "OPH_HELP_BEGIN $command"
        set value [help $command]
        puts $value
        puts "OPH_HELP_END $command"
    }
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live identity gate timeout"}
        after 100
    }
    if {[llength $opapp_databases] != 690 || [llength $opapp_tests] != 690} {error "Not exact690"}
    set opapp_databases [opapp_canonical $opapp_databases]
    set opapp_tests [opapp_canonical $opapp_tests]
    gui_open_cov -hier $op1144_design -testdir $opapp_databases -test $opapp_tests -merge OperandHierarchyDiagnostic690
    opapp_load_gate
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    foreach test $opapp_tests {puts $stream $test}
    close $stream
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) observations.tsv] w]
    puts $stream "stage\tscope\ttoken\tmetric\tvalue"
    close $stream
    set scopes [list ara_tb ara_tb.dut.i_ara_soc.i_system ara_tb.dut.i_ara_soc.i_system.i_ara [lindex $op1144_scopes 0] [lindex $op1144_scopes 4]]
    oph_fullroot
    op1144_save initial-empty.el 1
    op1144_audit raw 0
    gui_cov_show_value -switch false
    foreach scope $scopes {oph_observe raw_percent $scope}
    gui_exclusion_file -load -file [list $opapp_native]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native checksum review not empty"}
    op1144_audit applied 1
    op1144_save applied-before.el
    foreach scope $scopes {oph_observe applied_percent $scope}
    foreach scope $scopes {
        oph_fullroot
        set item [oph_find "" $scope 0]
        if {$item eq ""} {error "Missing selection scope"}
        gui_list_select -id CoverageTable.1 $scope
        set selected [gui_list_get_selected -id CoverageTable.1]
        set token [lindex [lindex $selected 0] 0]
        puts "OPH_SELECTION scope=$scope handle=$item selected=$selected token=$token"
        if {$token ne $scope} {error "Actual selected token differs"}
        gui_covtable_setroot -id CoverageTable.1 $token
        gui_process_events
        gui_cov_show_value -switch false
        oph_observe root_percent $scope
        gui_cov_show_value -switch true
        gui_process_events
        oph_observe root_ratio $scope
        gui_exclusion -id CoverageTable.1 -recalculate
        gui_process_events
        oph_observe recalculate_ratio $scope
        gui_cov_show_value -switch false
        gui_process_events
        oph_observe recalculate_percent $scope
    }
    oph_fullroot
    op1144_audit after 1
    op1144_save applied-after.el
    puts OPH_PROBE_DONE
}
if {![info exists oph_library_only]} {
set failed [catch {oph_session} message]
if {$failed} {puts "OPH_FAILED $message"; puts $::errorInfo}
set cleanup {}
if {[catch {gui_cov_show_value -switch false} detail]} {lappend cleanup $detail}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists op1144_scopes]} {
    if {[catch {oph_fullroot; op1144_audit final 0; op1144_save final-empty.el 1} detail]} {lappend cleanup $detail}
}
if {[llength $cleanup]} {puts "OPH_CLEANUP_FAILED $cleanup"}
if {!$failed && ![llength $cleanup]} {puts OPH_DONE_RESET}
gui_exit -noprompt
}
