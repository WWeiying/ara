# Single-test follow-up. Each rooted row is bound to a selected full-scope token.
set oph5_library_only 1
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/probe_operand_root_events.tcl

proc oph6_root_row {scope stage} {
    global env
    set expected [lindex [split $scope .] end]
    set item [gui_list_get -id CoverageTable.1 -firstChild]
    if {$item eq "" || $item eq "0"} {error "Missing rooted row"}
    set path [gui_list_get -id CoverageTable.1 -path $item]
    set name [gui_list_get -id CoverageTable.1 -text 0 $item]
    set sibling [gui_list_get -id CoverageTable.1 -nextSibling $item]
    if {$path ne $expected || $name ne $expected || ($sibling ne "" && $sibling ne "0")} {
        error "Root-row identity differs: requested=$scope path=$path name=$name sibling=$sibling"
    }
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) root-identities.tsv] a]
    puts $stream "$stage\t$scope\t$item\t$path\t$name"
    close $stream
    oph_write $stage $scope $item
    puts "OPH6_ROOT_ROW stage=$stage scope=$scope handle=$item path=$path"
    return $item
}
proc oph2_session {} {
    global env oph5_scopes op1144_scopes opapp_native
    if {$env(OPH_MODE) ne "pilot"} {error "One test only"}
    oph5_base_session
    set oph5_scopes [list ara_tb ara_tb.dut.i_ara_soc.i_system ara_tb.dut.i_ara_soc.i_system.i_ara [lindex $op1144_scopes 0] [lindex $op1144_scopes 4]]
    oph5_audit_subset raw 0
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) observations.tsv] w]
    puts $stream "stage\tscope\ttoken\tmetric\tvalue"
    close $stream
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) root-identities.tsv] w]
    puts $stream "stage\tscope\thandle\tpath\tname"
    close $stream
    gui_cov_show_value -switch false
    gui_process_events
    foreach scope $oph5_scopes {oph_observe raw $scope}
    gui_exclusion_file -load -file [list $opapp_native]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native review not empty"}
    op1144_save event-applied.el
    oph5_audit_subset applied 1
    foreach scope $oph5_scopes {
        oph2_fullroot
        set token [oph2_select $scope]
        puts "OPH6_SELECTED scope=$scope token=$token"
        gui_covtable_setroot -id CoverageTable.1 $token
        gui_process_events -mstime 100
        oph6_root_row $scope rooted
        gui_exclusion -id CoverageTable.1 -recalculate
        gui_process_events -mstime 100
        oph6_root_row $scope recalculate
        gui_exclusion -id CoverageTable.1 -update
        gui_process_events -mstime 100
        oph6_root_row $scope update
    }
    oph5_audit_subset after 1
    op1144_save event-after.el
    puts OPH6_ROOT_UPDATE_PROBE_DONE
}
if {![info exists oph6_library_only]} {
    set failed [catch {oph2_session} message]
    if {$failed} {puts "OPH2_FAILED $message"; puts $::errorInfo}
    set cleanup [oph2_cleanup]
    if {!$failed && ![llength $cleanup]} {puts OPH2_DONE_RESET}
    gui_exit -noprompt
}
