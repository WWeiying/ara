# Tcl8.4 read-only: no exclude/reset/load-EL calls.
proc pmp4_query {stream tag command} {
    puts $stream [join [list $tag [list $command]] "\t"]
    set bad [catch {uplevel #0 $command} value]
    puts $stream [join [list RESULT $bad [list $value]] "\t"]
    flush $stream
    return [list $bad $value]
}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/discover_ptw_pmp0_fsm_v2.tcl}
proc fp_normalize {value} {
    for {set n 0} {$n < 4} {incr n} {
        if {[catch {llength $value} count] || $count != 1} {break}
        set next [string trim [lindex $value 0]]
        if {$next eq $value} {break}
        set value $next
    }
    return $value
}
proc fp_session {} {
    global env
    set until [expr {[clock seconds]+60}]
    while {![file exists [file join $env(FSM_PROBE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $until} {error "No live identity gate"}
        after 100
    }
    gui_open_cov -hier $env(FSM_PROBE_DESIGN) -testdir [list $env(FSM_PROBE_SAMPLE)] -test [list $env(FSM_PROBE_SELECTED)] -merge ReadOnlyFSM741Sample
    set f [open [file join $env(FSM_PROBE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $f]
    close $f
    if {[string first "The design '$env(FSM_PROBE_DESIGN)' was loaded successfully." $log] < 0 || [regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:} $log]} {error "Historical load failed"}
    set stream [open [file join $env(FSM_PROBE_OUTPUT) native-token-api.tsv] {WRONLY CREAT EXCL}]
    puts $stream [list SINGLE_TEST $env(FSM_PROBE_SELECTED)]
    foreach cmd {gui_exclusion gui_exclude_items gui_exclusion_file gui_covdetail_select gui_list_get_selected gui_list_get_meta gui_dump_common_list} {
        pmp4_query $stream HELP [list help $cmd]
    }
    set tables {}
    foreach id [gui_get_window_ids] {if {[string match CoverageTable.* $id]} {lappend tables $id}}
    if {[llength $tables] != 1} {error "Ambiguous coverage table"}
    set id [lindex $tables 0]
    gui_list_expand -id $id -all {<root>}
    update
    set scope ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache.gen_rd_ports\[2\].genblk1.i_wt_dcache_ctrl
    puts $stream [list SCOPE $scope]
    gui_list_action -id $id -column FSM $scope
    update
    if {[gui_covdetail_query -id CovDetail.1 -name type] ne "FSM"} {error "Not FSM detail"}
    pmp4_query $stream NAMES {gui_list_get_selected -id CovDetail.1 -list fsmnames -all -flat}
    gui_list_select -id CovDetail.1 -list fsmnames -select {state_q}
    update
    if {[fp_normalize [gui_list_get_selected -id CovDetail.1 -list fsmnames -first]] ne "state_q"} {error "Wrong machine selection"}
    foreach mode {State Transition} {
        gui_covdetail_select -id CovDetail.1 -fsmMode $mode
        gui_covdetail_select -id CovDetail.1 -fsmShow List
        update
        pmp4_query $stream MODE_NAMES [list gui_list_get_selected -id CovDetail.1 -list {fsm list} -all -flat]
        pmp4_query $stream DUMP [list gui_dump_common_list -id CovDetail.1]
        set names [gui_list_get_selected -id CovDetail.1 -list {fsm list} -all -flat]
        set object [fp_normalize [lindex $names 0]]
        if {$object eq ""} {error "Empty FSM list"}
        gui_list_select -id CovDetail.1 -list {fsm list} -select [list $object]
        pmp4_query $stream SELECTED [list gui_list_get_selected -id CovDetail.1 -list {fsm list} -first]
        gui_list_select -id CovDetail.1 -list {fsm list} -unselect [list $object]
        pmp4v2_rows $stream
    }
    close $stream
    puts FSM741_READONLY_PROBE_DONE
}
if {![info exists fp_test_only]} {
    if {[catch {fp_session} message]} {puts "FSM741_READONLY_PROBE_FAILED $message\n$::errorInfo"}
    gui_exit -noprompt
}
