# Short readonly product scope probe. No native exclusion, reset, capture or qualification.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_batch_v5_library.tcl}
proc lpq_session {} {
    global env lpd_design lpd_testdirs lpd_tests lpd_children lpd_stream lpb_rows lpb_output lpa_binding lpa_expected
    global lpq_scope lpq_output lpn_global_before_complete
    set lpn_global_before_complete 0
    # Any parser/list-forwarding failure stops before design load or costly audit.
    lpn_preload
    source $env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION)
    source $env(LZC_SELECTOR_NATIVE_BATCH_SELECTION)
    source $env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS)
    source $env(LZC_SELECTOR_NATIVE_PROBE_SELECTION)
    lpd_require [expr {[llength $lpd_tests] == 707 && [llength $lpb_rows] == 4200 &&
        [array size lpa_binding] == 1200 && [array size lpa_expected] == 36}] "Sealed707 context required"
    set local {}
    foreach row $lpb_rows {if {[lindex $row 0] eq $lpq_scope} {lappend local $row}}
    lpd_require [expr {[llength $local] == 84}] "Exact first candidate child84 positions required"
    set matches {}
    foreach child $lpd_children {if {[lindex $child 0] eq $lpq_scope} {lappend matches $child}}
    lpd_require [expr {[llength $matches] == 1 && [lindex [lindex $matches 0] 1] eq "3250293308"}] "Exact child/module binding required"
    gui_open_cov -hier $lpd_design -testdir $lpd_testdirs -test $lpd_tests -merge LZC707GuardReadonlyShortScopeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_cov_show_cond_ids -show 0
    lpb_save [file join $lpq_output initial-empty.el] 1
    lpb_audit [file join $lpq_output scope-before.tsv] $local -1
    set lpd_stream [open [file join $lpq_output native-inventory.tcllist] w]
    set branches [lpd_branch $lpq_scope]
    set vectors [lpd_conditions $lpq_scope [lindex [lindex $matches 0] 3]]
    close $lpd_stream
    lpd_require [expr {$branches == 24 && $vectors == 60}] "Native child population differs"
    lpb_audit [file join $lpq_output scope-final.tsv] $local -1
    lpb_save [file join $lpq_output final-empty.el] 1
    lpd_require [expr {!$lpn_global_before_complete}] "Short probe must never open global qualification gate"
    puts LZC_NATIVE_GUARD_PROBE_COMPLETE_READONLY_NOT_QUALIFICATION
}
if {![info exists lpq_test_only]} {
    set failed [catch {lpq_session} message]
    if {[info exists lpd_stream]} {catch {close $lpd_stream}}
    if {$failed} {puts "LZC_NATIVE_GUARD_PROBE_FAILED $message\n$::errorInfo"}
    gui_exit -noprompt
}
