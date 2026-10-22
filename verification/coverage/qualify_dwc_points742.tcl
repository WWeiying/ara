# Local session only. Native names/handles, never raw indices, drive selection.
set fs_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_batch.tcl}
proc dw_need {ok message} {if {!$ok} {error $message}}
proc dw_save {name {empty 0}} {
    set path [file join $::env(DVE_COVERAGE_OUTPUT) $name]
    gui_exclusion_file -save -file [list $path]
    if {$empty && [file size $path] != 0} {error "Nonempty global exclusions: $name"}
}
proc dw_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc dw_select {token {meta {}}} {
    set old [gui_list_get_selected -id CovDetail.1 -flat]
    foreach item $old {
        set item [fp_normalize $item]
        if {$item eq "" || $item eq "{}"} {continue}
        gui_list_select -id CovDetail.1 -unselect [list $item]
    }
    dw_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Selection did not clear"
    gui_list_select -id CovDetail.1 -select [list $token]
    dw_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 1}] "Not a native singleton"
    set actual [fp_normalize [gui_list_get_selected -id CovDetail.1 -first]]
    dw_need [expr {$actual eq $token || ($meta ne "" && $actual eq $meta)}] "Native selection readback differs: $actual $token"
}
proc dw_walk {item stream} {
    global dw_rows dw_names dw_targets
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        puts $stream [join [list $item $path $meta $name] "\t"]
        foreach target $dw_targets {
            if {$meta eq $target || $name eq $target} {
                lappend dw_rows [list $path $meta $target]
                lappend dw_names $target
            }
        }
        dw_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc dw_bind {stage group index} {
    global dw_rows dw_names dw_targets
    p740_root
    set dw_targets [lindex $group 1]; set dw_rows {}; set dw_names {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $group 0]
    dw_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not native Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) toggle-${stage}-${index}.tsv] w]
    dw_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    dw_need [expr {[lsort $dw_names] eq [lsort $dw_targets]}] "Missing/duplicate native Toggle target: $dw_names"
    return $dw_rows
}
proc dw_audit {stage active} {
    global dw_groups dw_toggles dw_stream
    foreach group $dw_groups {
        fx_context $group
        foreach name [lindex $group 4] {
            fs_select $name
            set actual [gui_exclusion -id CovDetail.1 -list {fsm list} -excluded -selected]
            dw_need [expr {$actual eq "0" || $actual eq "1"}] "Invalid FSM Boolean"
            set want 0
            # State/arc GUI projections are not membership authority. Exact EL is.
            if {$active} {set want EL_AUTHORITY}
            puts $dw_stream [join [list $stage FSM [lindex $group 2] [lindex $group 3] $name $actual $want] "\t"]
            if {!$active && $actual ne "0"} {error "Reset FSM excluded: $name"}
        }
    }
    set index 0
    foreach group $dw_toggles {
        foreach row [dw_bind $stage $group $index] {
            dw_select [lindex $row 0] [lindex $row 1]
            set actual [gui_exclusion -id CovDetail.1 -excluded -selected]
            puts $dw_stream [join [list $stage Toggle [lindex $group 0] {} [lindex $row 2] $actual $active] "\t"]
            if {$actual ne "$active"} {error "Toggle membership differs: $row"}
        }
        incr index
    }
    flush $dw_stream
}
proc dw_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    gui_exclusion -id CoverageTable.1 -recalculate
    dw_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native exclusion review unresolved"
}
proc dw_session {} {
    global env dw_design dw_vdb dw_test dw_groups dw_toggles dw_stream dw_python dw_helper
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Actual executable gate absent"}
        after 100
    }
    gui_open_cov -hier $dw_design -testdir [list $dw_vdb] -test [list $dw_test] -merge DWCPrecise31And168
    set dw_stream [open [file join $env(DVE_COVERAGE_OUTPUT) audit.tsv] w]
    dw_save initial-empty.el 1
    dw_audit before 0
    foreach group $dw_groups {
        fx_context $group
        foreach name [lindex $group 5] {
            fs_select $name
            gui_exclude_items -id CovDetail.1 -list {fsm list} -selected -annotation {Frozen INCR-only DWC internal error route; exact reviewed FSM point}
        }
    }
    set index 0
    foreach group $dw_toggles {
        foreach row [dw_bind selection $group $index] {
            dw_select [lindex $row 0] [lindex $row 1]
            gui_exclude_items -id CovDetail.1 -selected -annotation {Frozen INCR-only DWC internal constant; interfaces retained}
        }
        incr index
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dw_save first.el
    puts [exec $dw_python -B $dw_helper el --output $env(DVE_COVERAGE_OUTPUT) --file first.el]
    dw_audit selected 1
    dw_reset
    dw_audit reset 0
    dw_save reset-empty.el 1
    dw_load first.el
    dw_audit reloaded 1
    dw_save second.el
    puts [exec $dw_python -B $dw_helper el --output $env(DVE_COVERAGE_OUTPUT) --file second.el]
    dw_reset
    dw_audit final 0
    dw_save final-empty.el 1
    close $dw_stream
    puts DWC_POINTS_NATIVE_DONE
}
if {![info exists dw_test_only]} {
    set failed [catch {dw_session} message]
    if {$failed} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream "$message\n$::errorInfo"; close $stream
        puts "DWC_POINTS_NATIVE_FAILED $message\n$::errorInfo"
    }
    if {[catch {dw_reset; dw_save cleanup-empty.el 1} cleanup]} {
        puts "DWC_POINTS_NATIVE_FAILED cleanup=$cleanup"
    }
    gui_exit -noprompt
}
