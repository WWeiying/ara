# Exact successor of pinned v1; only reload equivalence changes.
set qn_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qbs_full1792_qualification.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/native_exclusion_multiset_v2.tcl}
proc qnm_equal {first second} {
    # Retain the source allowlist/compiled checksum/vector and alias guards.
    qn_signature $first 0
    qn_signature $second 0
    set count [nem_require_equal [qs_bytes $first] [qs_bytes $second]]
    qbf_require [expr {$count == 1792}] "Exact1792 annotated native multiset required"
}
set qnm_old {qbf_require [expr {[qs_bytes [file join $qs_output first.el]] eq [qs_bytes [file join $qs_output second.el]]}] "Reload native signature drift"}
set qnm_new {qnm_equal [file join $qs_output first.el] [file join $qs_output second.el]}
set qnm_body [info body qn_run]
set qnm_position [string first $qnm_old $qnm_body]
qbf_require [expr {$qnm_position >= 0 && [string first $qnm_old $qnm_body [expr {$qnm_position + 1}]] < 0}] "Pinned v1 single replacement absent/ambiguous"
proc qn_run {} [string map [list $qnm_old $qnm_new] $qnm_body]
if {![info exists qnm_test_only]} {
    source $env(QBS_FULL1792_SELECTION)
    set qbf_stream [open [file join $qs_output native-qualification.tcllist] w]
    set failed [catch {
        gui_open_cov -hier $qs_design -testdir $qs_testdir -test $qs_test -merge QBSFull1792QualificationOnly
        gui_list_expand -id CoverageTable.1 -all {<root>}
        qn_run
    } message]
    set cleanup_failed [catch {gui_exclusion -reset; qn_save cleanup-empty.el 1} cleanup]
    qn_log [list terminal $failed $message $cleanup_failed $cleanup]
    close $qbf_stream
    if {$failed || $cleanup_failed} {puts "QBS_FULL1792_HOLD $message cleanup=$cleanup"} else {puts QBS_FULL1792_CAPTURED_PENDING_INDEPENDENT_INSPECT}
    gui_exit -noprompt
}
