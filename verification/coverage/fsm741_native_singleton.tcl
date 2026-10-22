set fp_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_native_probe.tcl}
proc fs_select {name} {
    set count [gui_list_get_selected -id CovDetail.1 -list {fsm list} -count]
    while {$count > 0} {
        set old [fp_normalize [gui_list_get_selected -id CovDetail.1 -list {fsm list} -first]]
        gui_list_select -id CovDetail.1 -list {fsm list} -unselect [list $old]
        set next [gui_list_get_selected -id CovDetail.1 -list {fsm list} -count]
        if {$next >= $count} {error "Selection did not clear"}
        set count $next
    }
    gui_list_select -id CovDetail.1 -list {fsm list} -select [list $name]
    update
    if {[gui_list_get_selected -id CovDetail.1 -list {fsm list} -count] != 1 || [fp_normalize [gui_list_get_selected -id CovDetail.1 -list {fsm list} -first]] ne $name} {error "Singleton selection differs"}
}
proc fs_context {scope} {
    gui_open_source -id CovDetail.1 -matrix Fsm -replace -active $scope -type Scope /home/wangwy/openproject/ara_dsa_signoff_integration/hardware/deps/cva6/core/cache_subsystem/wt_dcache_ctrl.sv
    gui_covdetail_select -id CovDetail.1 -name FSM
    gui_covdetail_select -id CovDetail.1 -region $scope -type Instance
    gui_covdetail_select -id CovDetail.1 -fsmShow List
    gui_covdetail_select -id CovDetail.1 -fsmMode State
    gui_list_select -id CovDetail.1 -list fsmnames -select state_q
    update
    if {[fp_normalize [gui_list_get_selected -id CovDetail.1 -list fsmnames -first]] ne "state_q"} {error "Wrong FSM machine"}
}
proc fs_save {name {empty 0}} {
    global env
    set path [file join $env(FSM_PROBE_OUTPUT) $name]
    gui_exclusion_file -save -file [list $path]
    if {$empty && [file size $path] != 0} {error "Expected empty exclusions"}
}
proc fs_audit {stage expected} {
    global fs_stream
    foreach name {IDLE KILL_MISS KILL_MISS_ACK MISS_REQ MISS_WAIT READ REPLAY_READ REPLAY_REQ} {
        fs_select $name
        set actual [gui_exclusion -id CovDetail.1 -list {fsm list} -excluded -selected]
        set want [expr {$expected && $name eq "KILL_MISS"}]
        puts $fs_stream [list $stage $name $actual $want]
        flush $fs_stream
        if {$actual != $want} {error "State exclusion differs: $stage $name"}
    }
}
proc fs_session {} {
    global env fs_stream
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(FSM_PROBE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live gate timed out"}
        after 100
    }
    gui_open_cov -hier $env(FSM_PROBE_DESIGN) -testdir [list $env(FSM_PROBE_SAMPLE)] -test [list $env(FSM_PROBE_SELECTED)] -merge FSM741Singleton
    set f [open [file join $env(FSM_PROBE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $f]; close $f
    if {[string first "The design '$env(FSM_PROBE_DESIGN)' was loaded successfully." $log] < 0 || [regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:} $log]} {error "Historical load failed"}
    set fs_stream [open [file join $env(FSM_PROBE_OUTPUT) singleton-audit.tsv] {WRONLY CREAT EXCL}]
    set scope {ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache.gen_rd_ports[2].genblk1.i_wt_dcache_ctrl}
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_list_action -id CoverageTable.1 -column FSM $scope
    update
    fs_context $scope
    fs_save initial.el 1
    fs_audit initial 0
    fs_select KILL_MISS
    gui_exclude_items -id CovDetail.1 -list {fsm list} -selected -annotation {Single disabled accelerator read-port state; format capture only}
    gui_exclusion -id CoverageTable.1 -recalculate
    fs_audit applied 1
    fs_save first.el
    gui_exclusion -reset
    fs_audit reset 0
    fs_save reset.el 1
    gui_exclusion_file -load -file [list [file join $env(FSM_PROBE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native load requires review"}
    fs_audit reloaded 1
    fs_save second.el
}
if {![info exists fs_test_only]} {
    set failed [catch {fs_session} message]
    if {$failed} {puts "FSM741_SINGLETON_FAILED $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists fs_stream]} {
        if {[catch {fs_audit final 0} detail]} {lappend cleanup $detail}
    }
    if {[catch {fs_save final-empty.el 1} detail]} {lappend cleanup $detail}
    if {[llength $cleanup]} {puts "FSM741_SINGLETON_FAILED cleanup=$cleanup"}
    if {!$failed && ![llength $cleanup]} {puts FSM741_SINGLETON_DONE}
    gui_exit -noprompt
}
