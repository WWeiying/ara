# Entry for the reviewed two-parent profile; no exclusion operations.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qbs_nested224_tree_probe.tcl}
proc qnt_session {} {
    global env qnt_scope qnt_parents qnt_stream qsd_design qsd_testdir qsd_test
    puts [list QBS_TREE_TCL_VERSION [info patchlevel] [info tclversion]]
    source $env(QBS_SIDE1792_SELECTION)
    set qnt_stream [open [file join $env(QBS_SIDE1792_OUTPUT) native-rows.tcllist] w]
    gui_open_cov -hier $qsd_design -testdir [list $qsd_testdir] -test [list $qsd_test] -merge QBSNestedTwoParentReadOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    qnt_probe
    close $qnt_stream
    puts QBS_NESTED_TWO_PARENT_COMPLETE_NATIVE_HOLD
}
if {![info exists qnt_test_only]} {
    set failed [catch {qnt_session} message]
    if {$failed} {puts "QBS_NESTED_TWO_PARENT_HOLD $message\n$::errorInfo"}
    if {[info exists qnt_stream]} {catch {close $qnt_stream}}
    gui_exit -noprompt
}
