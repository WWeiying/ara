# Tcl 8.4: one exact scope/test, queries only. Never exclusion/reset/load-EL.
proc pmp4_require {condition message} {if {!$condition} {error $message}}
proc pmp4_query {stream tag command} {
    puts $stream [join [list $tag [list $command]] "\t"]
    set bad [catch {uplevel #0 $command} value]
    puts $stream [join [list RESULT $bad [list $value]] "\t"]
    flush $stream
    return [list $bad $value]
}
proc pmp4_session {} {
    global env pmp4_design pmp4_test_vdb pmp4_test pmp4_scope
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable identity timeout"}
        after 100
    }
    gui_open_cov -hier $pmp4_design -testdir [list $pmp4_test_vdb] -test [list $pmp4_test] -merge PTWPMP4ReadOnly
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $stream]
    close $stream
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) load-gate.txt] w]
    puts $stream $log
    close $stream
    pmp4_require [expr {![regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Failed to load tests|Error:|Fatal:} $log] &&
                       [string first "The design '$pmp4_design' was loaded successfully." $log] >= 0}] "Coverage load failed"
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $pmp4_test
    close $stream
    set api [open [file join $env(DVE_COVERAGE_OUTPUT) native-api.txt] w]
    puts $api "Tcl [info patchlevel]"
    foreach command {gui_covdetail_select gui_covdetail_query gui_list_action gui_list_select gui_list_select_all gui_list_get_selected gui_list_get_meta gui_list_get_value gui_dump_common_list gui_list_get gui_list_get_property} {
        pmp4_query $api HELP [list help $command]
    }
    close $api
    set tables {}
    foreach id [gui_get_window_ids] {
        if {[string match CoverageTable.* $id]} {lappend tables $id}
    }
    pmp4_require [expr {[llength $tables] == 1}] "Not one summary table"
    set id [lindex $tables 0]
    gui_list_expand -id $id -all {<root>}
    update
    gui_list_action -id $id -column FSM $pmp4_scope
    update
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native-observations.tsv] w]
    puts $stream [join [list SCOPE $pmp4_scope] "\t"]
    puts $stream [join [list WINDOWS [list [gui_get_window_ids]]] "\t"]
    set result [pmp4_query $stream TYPE {gui_covdetail_query -id CovDetail.1 -name type}]
    pmp4_require [expr {[lindex $result 0] == 0 && [string equal -nocase [lindex $result 1] FSM]}] "Not FSM detail"
    pmp4_query $stream FSM_NAMES {gui_list_get_selected -id CovDetail.1 -list fsmnames -all -flat}
    pmp4_query $stream FSM_NAMES_COLUMNS {gui_list_get_selected -id CovDetail.1 -list fsmnames -all -flat -columns {Name Coverage}}
    pmp4_query $stream META {gui_list_get_meta -id CovDetail.1}
    pmp4_query $stream VALUES {gui_list_get_value -id CovDetail.1}
    # Select by compiled FSM name only, not by invented state/arc row IDs.
    set selection [pmp4_query $stream SELECT_STATE_Q {gui_list_select -id CovDetail.1 -list fsmnames -select {state_q}}]
    if {[lindex $selection 0] == 0} {
        update
        pmp4_query $stream SELECTED_FSM {gui_list_get_selected -id CovDetail.1 -list fsmnames -first}
        pmp4_query $stream FSM_NAMES_AFTER {gui_list_get_selected -id CovDetail.1 -list fsmnames -all -flat}
        pmp4_query $stream META_AFTER {gui_list_get_meta -id CovDetail.1}
        pmp4_query $stream VALUES_AFTER {gui_list_get_value -id CovDetail.1}
        pmp4_query $stream FIRST_CHILD {gui_list_get -id CovDetail.1 -firstChild}
    }
    close $stream
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) discovery-done] w]
    puts $stream PTW_FSM_READONLY_DISCOVERY_DONE
    close $stream
    puts PTW_FSM_READONLY_DISCOVERY_DONE
}
set failed [catch {pmp4_session} message]
if {$failed} {puts "PTW_FSM_READONLY_DISCOVERY_FAILED $message\n$::errorInfo"}
gui_exit -noprompt
