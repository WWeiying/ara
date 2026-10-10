source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qbs_full_nested_native_body.tcl}
proc qbf_session {} {
    global env qbf_stream qsd_design qsd_testdir qsd_test qbf_scopes
    puts [list QBS_FULL_TREE_TCL [info patchlevel] [info tclversion]]
    source $env(QBS_SIDE1792_SELECTION)
    qbf_require [expr {[llength $qbf_scopes] == 2}] "Exact two-bank profile"
    set qbf_stream [open [file join $env(QBS_SIDE1792_OUTPUT) native-rows.tcllist] w]
    gui_open_cov -hier $qsd_design -testdir [list $qsd_testdir] -test [list $qsd_test] -merge QBSFullNestedReadOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    foreach scope $qbf_scopes {qbf_scope [lindex $scope 0] [lindex $scope 1]}
    qbf_emit [list complete 1344 448 FULL1792_NATIVE_HOLD]
    close $qbf_stream
    puts QBS_FULL_NESTED_DISCOVERY_COMPLETE_NATIVE_HOLD
}
if {![info exists qbf_test_only]} {
    set failed [catch {qbf_session} message]
    if {$failed} {puts "QBS_FULL_NESTED_HOLD $message\n$::errorInfo"}
    if {[info exists qbf_stream]} {catch {close $qbf_stream}}
    gui_exit -noprompt
}
