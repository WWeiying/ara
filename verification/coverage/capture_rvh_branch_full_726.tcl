# Tcl8.4. Temporary full247 measurement, never population application.
proc rvh_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_keys dbg_targets dbg_python dbg_driver
    global rvh_annotation rvh_capture_gate
    source [file join $env(DVE_COVERAGE_OUTPUT) branch-library.tcl]
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    dbg_require [expr {[llength $dbg_scopes] == 14}] "Exact14 scopes required"
    set count 0
    set targets 0
    foreach scope $dbg_scopes {
        incr count [llength $dbg_keys($scope|branch)]
        incr targets [llength $dbg_targets($scope|branch)]
    }
    dbg_require [expr {$count == 1780 && $targets == 247}] "Full247/1780 required"
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable gate timed out"}
        after 100
    }
    set dirs [glob -types d -directory [file join $dbg_test snps coverage db testdata] *]
    dbg_require [expr {[llength $dirs] == 1}] "One admitted measurement sample required"
    set test [file join [file rootname $dbg_test] [file tail [lindex $dirs 0]]]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    gui_open_cov -hier $dbg_design -testdir [list $dbg_test] -test [list $test] -merge RVHFull247NativeQualificationOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    dbg_save initial-empty.el 1
    dbg_audit before 0
    set rvh_capture_gate 1
    foreach scope $dbg_scopes {
        array unset metadata
        array set metadata [dbg_metadata $scope branch]
        foreach key $dbg_targets($scope|branch) {
            dbg_require [expr {$rvh_capture_gate == 1 && [info exists metadata($key)]}] "Before/native binding gate closed"
            dbg_select branch [lindex $metadata($key) 0]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation $rvh_annotation
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native selection review not empty"
    dbg_audit selected 1
    dbg_save first.el
    puts [exec $dbg_python -B $dbg_driver first --output $env(DVE_COVERAGE_OUTPUT) --seal $env(RVH_CAPTURE_SEAL)]
    gui_exclusion -reset
    dbg_audit reset 0
    dbg_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native reload review not empty"
    dbg_audit reloaded 1
    dbg_save second.el
}
if {![info exists rvh_library_only]} {
    set failed [catch {rvh_session} message]
    if {$failed} {puts "RVH_FULL_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[llength [info commands dbg_audit]] && [info exists dbg_scopes]} {
        if {[catch {dbg_audit final 0} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Missing initialized full1780 audit}}
    if {[llength [info commands dbg_save]]} {
        if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Missing native save helper}}
    if {$failed || [llength $cleanup]} {puts "RVH_FULL_FAILED $message cleanup=$cleanup"} else {
        puts DBG_CAPTURE_DONE
        puts RVH_FULL_DONE_EXACT247
    }
    gui_exit -noprompt
}
