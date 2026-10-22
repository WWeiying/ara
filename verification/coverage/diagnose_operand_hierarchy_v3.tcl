# Preserve v2; normalize the real empty-selection list before explicit selection.
set oph2_library_only 1
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/diagnose_operand_hierarchy_v2.tcl
proc oph2_select {scope} {
    set old [gui_list_get_selected -id CoverageTable.1 -flat]
    set clear {}
    foreach item $old {if {[string trim $item] ne ""} {lappend clear $item}}
    puts "OPH3_OLD_SELECTION raw=$old normalized=$clear"
    if {[llength $clear]} {gui_list_select -id CoverageTable.1 -unselect $clear}
    gui_list_select -id CoverageTable.1 -select [list $scope]
    set actual [gui_list_get_selected -id CoverageTable.1 -flat]
    puts "OPH3_NEW_SELECTION wanted=$scope actual=$actual"
    if {[llength $actual] != 1 || [lindex $actual 0] ne $scope} {
        error "Exact table selection differs: $actual wanted $scope"
    }
    return [lindex $actual 0]
}
if {![info exists oph3_library_only]} {
    set failed [catch {oph2_session} message]
    if {$failed} {puts "OPH2_FAILED $message"; puts $::errorInfo}
    set cleanup [oph2_cleanup]
    if {!$failed && ![llength $cleanup]} {puts OPH2_DONE_RESET}
    gui_exit -noprompt
}
