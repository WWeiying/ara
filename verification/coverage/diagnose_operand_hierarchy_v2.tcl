# Separate corrected probe; earlier failed hook and artifacts remain pinned.
proc oph2_load {} {
    global env oph_library_only opapp_library_only
    set oph_library_only 1
    set opapp_library_only 1
    source $env(OPH_V1_HOOK)
    source $env(OPH_APP_HOOK)
    opapp_load
}
proc oph2_fullroot {} {
    gui_covtable_show -id CoverageTable.1 -show {Design Hierarchy} -cumulative 1
    gui_covtable_setroot -id CoverageTable.1 ara_tb
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_process_events
}
proc oph2_select {scope} {
    set old [gui_list_get_selected -id CoverageTable.1 -flat]
    if {[llength $old]} {gui_list_select -id CoverageTable.1 -unselect $old}
    gui_list_select -id CoverageTable.1 -select [list $scope]
    set actual [gui_list_get_selected -id CoverageTable.1 -flat]
    if {[llength $actual] != 1 || [lindex $actual 0] ne $scope} {
        error "Exact table selection differs: $actual wanted $scope"
    }
    return [lindex $actual 0]
}
proc oph2_query_all {stage} {
    global env op1144_scopes
    oph2_fullroot
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) queryable_$stage.tsv] w]
    puts $stream "scope\thandle\ttoken\tbranch_coordinates"
    set failed [catch {
        foreach scope $op1144_scopes {
            set item [oph_find "" $scope 0]
            if {$item eq ""} {error "Unqueryable scope: $scope"}
            set token [oph2_select $scope]
            set metadata [op1144_metadata $token]
            if {[llength $metadata] != 202} {error "Not full101 branch inventory"}
            puts $stream "$scope\t$item\t$token\t101"
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "OPH2_QUERY_ALL $stage 36"
}
proc oph2_snapshot {stage scopes} {
    gui_cov_show_value -switch false
    gui_process_events
    foreach scope $scopes {oph_observe ${stage}_percent $scope}
    gui_cov_show_value -switch true
    gui_process_events
    foreach scope $scopes {oph_observe ${stage}_ratio $scope}
    gui_cov_show_value -switch false
}
proc oph2_session {} {
    global env op1144_design op1144_test op1144_keys op1144_targets op1144_scopes
    global opapp_databases opapp_tests opapp_native
    oph2_load
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    foreach command {gui_covtable_setroot gui_covtable_show gui_list_expand gui_list_select gui_list_get_selected gui_list_get gui_cov_show_value gui_process_events gui_exclusion} {
        puts "OPH2_HELP_BEGIN $command"
        puts [help $command]
        puts "OPH2_HELP_END $command"
    }
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live gate timeout"}
        after 100
    }
    if {[llength $opapp_databases] != 690 || [llength $opapp_tests] != 690} {error "Not exact690 source"}
    if {$env(OPH_MODE) eq "pilot"} {
        set opapp_databases [lrange $opapp_databases 0 0]
        set opapp_tests [lrange $opapp_tests 0 0]
    } elseif {$env(OPH_MODE) ne "full"} {error "Invalid probe mode"}
    set opapp_databases [opapp_canonical $opapp_databases]
    set opapp_tests [opapp_canonical $opapp_tests]
    gui_open_cov -hier $op1144_design -testdir $opapp_databases -test $opapp_tests -merge OperandHierarchyProbeV2
    opapp_load_gate
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    foreach test $opapp_tests {puts $stream $test}
    close $stream
    op1144_save initial-empty.el 1
    oph2_query_all before
    if {$env(OPH_MODE) eq "pilot"} {puts OPH2_MINIMAL_QUERY_PASSED; return}
    # Only after all36 scopes are queryable may the sealed singleton audit run.
    op1144_audit raw 0
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) observations.tsv] w]
    puts $stream "stage\tscope\ttoken\tmetric\tvalue"
    close $stream
    set scopes [list ara_tb ara_tb.dut.i_ara_soc.i_system ara_tb.dut.i_ara_soc.i_system.i_ara [lindex $op1144_scopes 0] [lindex $op1144_scopes 4]]
    oph2_snapshot raw $scopes
    gui_exclusion_file -load -file [list $opapp_native]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native checksum review not empty"}
    op1144_audit applied 1
    op1144_save applied-before.el
    oph2_snapshot applied $scopes
    foreach scope $scopes {
        oph2_fullroot
        set item [oph_find "" $scope 0]
        if {$item eq ""} {error "Missing scope before root change"}
        set token [oph2_select $scope]
        puts "OPH2_SELECTION scope=$scope handle=$item token=$token"
        gui_covtable_setroot -id CoverageTable.1 $token
        gui_process_events
        oph2_snapshot root [list $scope]
        gui_exclusion -id CoverageTable.1 -recalculate
        gui_process_events
        oph2_snapshot recalculate [list $scope]
    }
    oph2_query_all after
    op1144_audit after 1
    op1144_save applied-after.el
    puts OPH2_FULL_PROBE_PASSED
}
proc oph2_cleanup {} {
    global env op1144_scopes
    set errors {}
    foreach step {display reset root query audit save} {
        set failed [catch {
            switch -- $step {
                display {gui_cov_show_value -switch false}
                reset {gui_exclusion -reset}
                root {oph2_fullroot}
                query {if {[info exists op1144_scopes]} {oph2_query_all final}}
                audit {if {$env(OPH_MODE) eq "full" && [info exists op1144_scopes]} {op1144_audit final 0}}
                save {if {[info procs op1144_save] ne ""} {op1144_save final-empty.el 1}}
            }
        } message]
        if {$failed} {lappend errors [list $step $message]; puts "OPH2_CLEANUP_ERROR $step $message"}
    }
    return $errors
}
if {![info exists oph2_library_only]} {
    set failed [catch {oph2_session} message]
    if {$failed} {puts "OPH2_FAILED $message"; puts $::errorInfo}
    set cleanup [oph2_cleanup]
    if {!$failed && ![llength $cleanup]} {puts OPH2_DONE_RESET}
    gui_exit -noprompt
}
