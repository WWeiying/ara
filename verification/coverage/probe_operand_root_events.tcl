# Minimal one-test root contract and event-only observation; no corpus report.
set oph4_library_only 1
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/diagnose_operand_hierarchy_v4.tcl
rename oph2_session oph5_base_session
rename oph2_cleanup oph5_base_cleanup

proc oph5_dump_rows {stream request parent depth} {
    global oph5_rows
    if {$depth > 1} {return}
    if {$parent eq ""} {set item [gui_list_get -id CoverageTable.1 -firstChild]} else {
        set item [gui_list_get -id CoverageTable.1 -firstChild $parent]
    }
    set siblings 0
    while {$item ne "" && $item ne "0" && $siblings < 12} {
        set path [gui_list_get -id CoverageTable.1 -path $item]
        set name [gui_list_get -id CoverageTable.1 -text 0 $item]
        foreach field [list $request $path $name] {if {[regexp {[\t\r\n]} $field]} {error "Non TSV root field"}}
        puts $stream "$request\t$depth\t$item\t$path\t$name"
        incr oph5_rows
        oph5_dump_rows $stream $request $item [expr {$depth+1}]
        incr siblings
        set item [gui_list_get -id CoverageTable.1 -nextSibling $item]
    }
}
proc oph5_audit_subset {stage active} {
    global env oph5_scopes op1144_keys op1144_targets
    oph2_fullroot
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) subset_$stage.tsv] w]
    puts $stream "scope\tcoordinate\tmeta\tpath\texcluded"
    set failed [catch {
        foreach scope [lrange $oph5_scopes 3 4] {
            array unset metadata
            array set metadata [op1144_metadata $scope]
            foreach key $op1144_keys($scope) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                op1144_select [list $meta]
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                set wanted [expr {$active && [lsearch -exact $op1144_targets($scope) $key] >= 0}]
                if {($actual ne "0" && $actual ne "1") || $actual != $wanted} {error "Subset singleton state differs"}
                puts $stream "$scope\t$key\t$meta\t$path\t$actual"
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "OPH5_SUBSET_AUDIT $stage 202"
}
proc oph5_fixed_read {stage} {
    global oph5_scopes oph5_handles
    foreach scope $oph5_scopes {
        set item $oph5_handles($scope)
        if {[gui_list_get -id CoverageTable.1 -path $item] ne $scope} {error "Event-phase handle identity changed"}
        oph_write $stage $scope $item
    }
}
proc oph2_session {} {
    global env oph5_scopes oph5_handles oph5_rows op1144_scopes opapp_native
    if {$env(OPH_MODE) ne "pilot"} {error "Single-test only"}
    oph5_base_session
    set oph5_scopes [list ara_tb ara_tb.dut.i_ara_soc.i_system ara_tb.dut.i_ara_soc.i_system.i_ara [lindex $op1144_scopes 0] [lindex $op1144_scopes 4]]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) root-contract.tsv] w]
    puts $stream "request\tdepth\thandle\tpath\tname"
    set failed [catch {
        foreach scope $oph5_scopes {
            oph2_fullroot
            set token [oph2_select $scope]
            gui_covtable_setroot -id CoverageTable.1 $token
            gui_process_events
            set oph5_rows 0
            oph5_dump_rows $stream $scope "" 0
            if {$oph5_rows == 0} {error "Empty relocated table: $scope"}
            puts "OPH5_ROOT_CONTRACT request=$scope token=$token rows=$oph5_rows"
        }
    } message]
    close $stream
    if {$failed} {error $message}
    oph5_audit_subset raw 0
    gui_cov_show_value -switch false
    gui_process_events
    foreach scope $oph5_scopes {
        set item [oph_find "" $scope 0]
        if {$item eq ""} {error "Missing fixed-read scope"}
        set oph5_handles($scope) $item
    }
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) observations.tsv] w]
    puts $stream "stage\tscope\ttoken\tmetric\tvalue"
    close $stream
    oph5_fixed_read raw
    gui_exclusion_file -load -file [list $opapp_native]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native review not empty"}
    # No tree lookup, display switch, root change, sleep, or audit between reads.
    oph5_fixed_read immediate_a
    oph5_fixed_read immediate_b
    gui_process_events -mstime 100
    oph5_fixed_read events_100
    gui_process_events -mstime 100
    oph5_fixed_read events_200
    op1144_save event-applied.el
    oph5_audit_subset applied 1
    op1144_save event-after.el
    puts OPH5_ROOT_EVENT_PROBE_DONE
}
proc oph2_cleanup {} {
    global oph5_scopes
    set errors [oph5_base_cleanup]
    if {[info exists oph5_scopes]} {
        if {[catch {oph5_audit_subset final 0} message]} {lappend errors [list subset_final $message]; puts "OPH2_CLEANUP_ERROR subset_final $message"}
    }
    return $errors
}
if {![info exists oph5_library_only]} {
    set failed [catch {oph2_session} message]
    if {$failed} {puts "OPH2_FAILED $message"; puts $::errorInfo}
    set cleanup [oph2_cleanup]
    if {!$failed && ![llength $cleanup]} {puts OPH2_DONE_RESET}
    gui_exit -noprompt
}
