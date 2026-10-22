# CoverageTable -flat still returns one group containing the selected token.
set oph2_library_only 1
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/diagnose_operand_hierarchy_v2.tcl
proc oph4_tokens {raw} {
    if {[llength $raw] == 0} {return {}}
    if {[llength $raw] != 1} {error "Multiple selection groups: $raw"}
    set group [lindex $raw 0]
    if {[llength $group] > 1} {error "Multiple selection tokens: $raw"}
    if {[llength $group] == 0} {return {}}
    return [list [lindex $group 0]]
}
proc oph2_select {scope} {
    set old [gui_list_get_selected -id CoverageTable.1 -flat]
    set clear [oph4_tokens $old]
    puts "OPH4_OLD_SELECTION raw=$old normalized=$clear"
    if {[llength $clear]} {gui_list_select -id CoverageTable.1 -unselect $clear}
    gui_list_select -id CoverageTable.1 -select [list $scope]
    set raw [gui_list_get_selected -id CoverageTable.1 -flat]
    set actual [oph4_tokens $raw]
    puts "OPH4_NEW_SELECTION wanted=$scope raw=$raw actual=$actual"
    if {[llength $actual] != 1 || [lindex $actual 0] ne $scope} {error "Exact selected scope differs"}
    return [lindex $actual 0]
}
if {![info exists oph4_library_only]} {
    set failed [catch {oph2_session} message]
    if {$failed} {puts "OPH2_FAILED $message"; puts $::errorInfo}
    set cleanup [oph2_cleanup]
    if {!$failed && ![llength $cleanup]} {puts OPH2_DONE_RESET}
    gui_exit -noprompt
}
