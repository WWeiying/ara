# Tcl8.4. Local point-only qualification, no population or whole-scope exclusion.
proc a137_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_keys dbg_targets dbg_python dbg_driver
    global a137_annotation a137_pythonpath
    source [file join $env(DVE_COVERAGE_OUTPUT) branch-library.tcl]
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    dbg_require [expr {[llength $dbg_scopes] == 4}] "Four exact AluA scopes required"
    set targets 0; set total 0
    foreach scope $dbg_scopes {
        incr total [llength $dbg_keys($scope|branch)]
        incr targets [llength $dbg_targets($scope|branch)]
    }
    dbg_require [expr {$targets == 137 && $total == 404}] "Exact137/full404 required"
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable gate timeout"}
        after 100
    }
    set dirs [glob -types d -directory [file join $dbg_test snps coverage db testdata] *]
    dbg_require [expr {[llength $dirs] == 1}] "One admitted measurement sample"
    set test [file join [file rootname $dbg_test] [file tail [lindex $dirs 0]]]
    set f [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w];puts $f $test;close $f
    gui_open_cov -hier $dbg_design -testdir [list $dbg_test] -test [list $test] -merge AluA137LocalOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    dbg_save initial-empty.el 1
    dbg_audit before 0
    foreach scope $dbg_scopes {
        array unset metadata
        array set metadata [dbg_metadata $scope branch]
        foreach key $dbg_targets($scope|branch) {
            dbg_require [expr {[info exists metadata($key)]}] "Actual native selector missing"
            dbg_select branch [lindex $metadata($key) 0]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation $a137_annotation
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Selection review not empty"
    dbg_audit selected 1
    dbg_save first.el
    puts [exec /usr/bin/env PYTHONPATH=$a137_pythonpath $dbg_python -B $dbg_driver first --output $env(DVE_COVERAGE_OUTPUT) --seal $env(A137_CAPTURE_SEAL)]
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_audit reset 0
    dbg_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload review not empty"
    dbg_audit reloaded 1
    dbg_save second.el
}
if {![info exists a137_library_only]} {
    set failed [catch {a137_session} message]
    if {$failed} {puts "ALUA137_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[catch {gui_exclusion -id CoverageTable.1 -recalculate} detail]} {lappend cleanup $detail}
    if {[catch {dbg_audit final 0} detail]} {lappend cleanup $detail}
    if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
    if {$failed || [llength $cleanup]} {puts "ALUA137_FAILED $message cleanup=$cleanup"} else {
        puts DBG_CAPTURE_DONE
        puts ALUA137_FIVE_STAGE_DONE
    }
    gui_exit -noprompt
}
