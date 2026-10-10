# Read-only successor: product child paths require an expanded coverage hierarchy.
set lpd_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_discover.tcl}
proc lpd_session {} {
    global env lpd_stream lpd_design lpd_testdirs lpd_tests lpd_children
    source $env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION)
    lpd_require [expr {[llength $lpd_tests] == 707 && [llength $lpd_children] == 36}] "Exact approved population required"
    set lpd_stream [open [file join $env(LZC_SELECTOR_NATIVE_PRODUCT_OUTPUT) native-inventory.tcllist] w]
    gui_open_cov -hier $lpd_design -testdir $lpd_testdirs -test $lpd_tests -merge LZC707ProductReadOnlyDiscovery
    gui_list_expand -id CoverageTable.1 -all {<root>}
    lpd_emit [list population $lpd_design $lpd_testdirs $lpd_tests]
    foreach child $lpd_children {
        set scope [lindex $child 0]
        lpd_require [expr {[lindex $child 1] eq "3250293308"}] "Product module checksum binding differs"
        lpd_emit [list child_binding $scope [lindex $child 1] [lindex $child 2]]
        set branches [lpd_branch $scope]
        set vectors [lpd_conditions $scope [lindex $child 3]]
        lpd_emit [list child_complete $scope $branches $vectors]
        puts "LZC_PRODUCT_READONLY_CHILD_COMPLETE $scope branch=$branches vector=$vectors"
    }
    close $lpd_stream
    puts LZC_PRODUCT_READONLY_DISCOVERY_COMPLETE
}
if {![info exists lpd_v3_test_only]} {
    set failed [catch {lpd_session} message]
    if {[info exists lpd_stream]} {catch {close $lpd_stream}}
    if {$failed} {puts "LZC_PRODUCT_READONLY_DISCOVERY_FAILED $message\n$::errorInfo"}
    gui_exit -noprompt
}
