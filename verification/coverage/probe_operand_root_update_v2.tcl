# Preserve the update API error as evidence; never promote it to success.
set oph6_library_only 1
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/probe_operand_root_update.tcl
proc oph7_update {scope} {
    global env
    set code [catch {gui_exclusion -id CoverageTable.1 -update} result]
    set detail ""
    if {$code} {set detail $::errorInfo}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) update-attempts.tsv] a]
    set escaped [string map [list "\t" {\t} "\r" {\r} "\n" {\n}] $detail]
    puts $stream "$scope\t$code\t$result\t$escaped"
    close $stream
    puts "OPH7_UPDATE_ATTEMPT scope=$scope code=$code result=$result"
    gui_process_events -mstime 100
    oph6_root_row $scope update
}
proc oph2_session {} {
    global env oph5_scopes op1144_scopes opapp_native
    if {$env(OPH_MODE) ne "pilot"} {error "One test only"}
    oph5_base_session
    set oph5_scopes [list ara_tb ara_tb.dut.i_ara_soc.i_system ara_tb.dut.i_ara_soc.i_system.i_ara [lindex $op1144_scopes 0] [lindex $op1144_scopes 4]]
    oph5_audit_subset raw 0
    foreach name {observations root-identities update-attempts} {
        set stream [open [file join $env(DVE_COVERAGE_OUTPUT) $name.tsv] w]
        switch -- $name {
            observations {puts $stream "stage\tscope\ttoken\tmetric\tvalue"}
            root-identities {puts $stream "stage\tscope\thandle\tpath\tname"}
            update-attempts {puts $stream "scope\tcatch_code\tresult\terror_info"}
        }
        close $stream
    }
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
        oph7_update $scope
    }
    oph5_audit_subset after 1
    op1144_save event-after.el
    puts OPH6_ROOT_UPDATE_PROBE_DONE
}
if {![info exists oph7_library_only]} {
    set failed [catch {oph2_session} message]
    if {$failed} {puts "OPH2_FAILED $message"; puts $::errorInfo}
    set cleanup [oph2_cleanup]
    if {!$failed && ![llength $cleanup]} {puts OPH2_DONE_RESET}
    gui_exit -noprompt
}
