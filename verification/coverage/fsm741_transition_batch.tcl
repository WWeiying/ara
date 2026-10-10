set fs_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_native_singleton.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}
proc fx_context {group} {
    set scope [lindex $group 0]
    p740_root
    gui_list_action -id CoverageTable.1 -column FSM $scope
    update
    gui_open_source -id CovDetail.1 -matrix Fsm -replace -active $scope -type Scope [lindex $group 1]
    gui_covdetail_select -id CovDetail.1 -name FSM
    gui_covdetail_select -id CovDetail.1 -region $scope -type Instance
    gui_covdetail_select -id CovDetail.1 -fsmShow List
    gui_covdetail_select -id CovDetail.1 -fsmMode [lindex $group 3]
    set count [gui_list_get_selected -id CovDetail.1 -list fsmnames -count]
    while {$count > 0} {
        set old [fp_normalize [gui_list_get_selected -id CovDetail.1 -list fsmnames -first]]
        gui_list_select -id CovDetail.1 -list fsmnames -unselect [list $old]
        set next [gui_list_get_selected -id CovDetail.1 -list fsmnames -count]
        if {$next >= $count} {error "Machine selection did not clear"}
        set count $next
    }
    gui_list_select -id CovDetail.1 -list fsmnames -select [list [lindex $group 2]]
    update
    if {[gui_list_get_selected -id CovDetail.1 -list fsmnames -count] != 1 || [fp_normalize [gui_list_get_selected -id CovDetail.1 -list fsmnames -first]] ne [lindex $group 2]} {error "Wrong native FSM machine"}
    set actual [gui_list_get_selected -id CovDetail.1 -list {fsm list} -all -flat]
    # -all means all only when no selection: clear first before inventory.
    set count [gui_list_get_selected -id CovDetail.1 -list {fsm list} -count]
    while {$count > 0} {
        set old [fp_normalize [gui_list_get_selected -id CovDetail.1 -list {fsm list} -first]]
        gui_list_select -id CovDetail.1 -list {fsm list} -unselect [list $old]
        set next [gui_list_get_selected -id CovDetail.1 -list {fsm list} -count]
        if {$next >= $count} {error "Native inventory selection did not clear"}
        set count $next
    }
    set actual [gui_list_get_selected -id CovDetail.1 -list {fsm list} -all -flat]
    while {[llength $actual] == 1 && [llength [lindex $actual 0]] > 1} {set actual [lindex $actual 0]}
    set names {}
    foreach name $actual {lappend names [fp_normalize $name]}
    if {[lsort $names] ne [lsort [lindex $group 4]] || [llength [lsort -unique $names]] != [llength $names]} {error "Native compiled inventory differs: $scope [lindex $group 2] [lindex $group 3]: $names"}
}
proc fx_audit {stage expected} {
    global fx_groups fx_stream
    set mismatches {}
    foreach group $fx_groups {
        fx_context $group
        foreach name [lindex $group 4] {
            fs_select $name
            set actual [gui_exclusion -id CovDetail.1 -list {fsm list} -excluded -selected]
            set observe [expr {$expected && [lindex $group 3] eq "State"}]
            set want [expr {$expected && [lsearch -exact [lindex $group 5] $name] >= 0}]
            if {$observe} {set want INHERITED_OBSERVATION}
            puts $fx_stream [join [list $stage [lindex $group 0] [lindex $group 2] [lindex $group 3] $name $actual $want] "\t"]
            flush $fx_stream
            if {($observe && $actual ne "0" && $actual ne "1") || (!$observe && $actual != $want)} {lappend mismatches [list [lindex $group 0] [lindex $group 2] [lindex $group 3] $name $actual $want]}
        }
    }
    if {[llength $mismatches]} {error "Native target/protected mismatches: $stage $mismatches"}
}
proc fx_session {} {
    global env fx_groups fx_stream p740_scopes p740_root_names
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live gate timed out"}
        after 100
    }
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    set p740_scopes [list ara_tb.dut.i_ara_soc.i_system]
    set p740_root_names(ara_tb.dut.i_ara_soc.i_system) i_system
    fs_save initial.el 1
    fx_audit initial 0
    p740_summary raw
    foreach group $fx_groups {
        fx_context $group
        foreach name [lindex $group 5] {
            fs_select $name
            gui_exclude_items -id CovDetail.1 -list {fsm list} -selected -annotation {Frozen configuration/source-proven FSM point; exact three-group scope}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    fs_save first.el
    fx_audit applied 1
    p740_summary applied
    gui_exclusion -reset
    fx_audit reset 0
    fs_save reset.el 1
    p740_summary reset
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native import unresolved"}
    fx_audit reloaded 1
    fs_save second.el
    p740_summary reloaded
    gui_exclusion -reset
    fx_audit final 0
    fs_save final-empty.el 1
    p740_summary final
}
proc apply_reviewed_waivers {id} {
    if {$id ne "CoverageTable.1"} {error "Unexpected table"}
    set failed [catch {fx_session} message]
    if {$failed} {puts "FSM741_EXACT_FAILED $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[catch {fs_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {$failed || [llength $cleanup]} {error "FSM741_EXACT_FAILED session=$message cleanup=$cleanup"}
    puts FSM741_EXACT_DONE
}
