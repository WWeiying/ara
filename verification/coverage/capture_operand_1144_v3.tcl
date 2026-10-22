# Absolute pinned source only; DVE info script is diagnostic, never a path base.
set op1144_v3_run [expr {![info exists op1144_library_only]}]
proc op1144_v3_procs {} {
    foreach name {op1144_require op1144_select op1144_metadata op1144_audit op1144_save op1144_session} {
        if {[info procs $name] ne $name} {error "Required helper proc missing: $name"}
    }
}
proc op1144_v3_load {} {
    global env op1144_library_only
    if {![info exists env(OP1144_BASE_HOOK)]} {error "Absolute pinned helper environment missing"}
    set path $env(OP1144_BASE_HOOK)
    puts [list OP1144_SOURCE_CONTEXT [info script] [pwd] $path]
    if {[file pathtype $path] ne "absolute" || ![file isfile $path]} {error "Pinned helper path invalid"}
    foreach name {op1144_require op1144_select op1144_metadata op1144_audit op1144_save op1144_session} {
        if {[llength [info commands $name]]} {error "Pre-existing helper collision: $name"}
    }
    set op1144_library_only 1
    set failed [catch {source $path} message]
    if {$failed} {error "Pinned helper source failed: $message"}
    op1144_v3_procs
}
set op1144_v3_load_failed [catch {op1144_v3_load} op1144_v3_load_message]
if {!$op1144_v3_load_failed} {
proc op1144_session {} {
    global env op1144_design op1144_test op1144_scopes op1144_targets op1144_keys
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    puts OP1144_WAITING_FOR_LIVE_IDENTITY
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable identity gate timed out"}
        after 100
    }
    set dirs [glob -types d -directory [file join $op1144_test snps coverage db testdata] *]
    op1144_require [expr {[llength $dirs] == 1}] "Requires one selected test"
    set test [file join [file rootname $op1144_test] [file tail [lindex $dirs 0]]]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    gui_open_cov -hier $op1144_design -testdir [list $op1144_test] -test [list $test] -merge Operand1144IdentityOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    op1144_save initial-empty.el 1
    op1144_audit before 0
    foreach scope $op1144_scopes {
        array unset metadata
        array set metadata [op1144_metadata $scope]
        foreach key $op1144_targets($scope) {
            op1144_select [list [lindex $metadata($key) 0]]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation {Operand parameter native discovery; exact vectors only; not application approval}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    op1144_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Initial selection needs review"
    op1144_audit selected 1
    op1144_save first.el
    gui_exclusion -reset
    op1144_audit reset 0
    op1144_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    op1144_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Roundtrip requires review"
    op1144_audit reloaded 1
    op1144_save second.el
}

if {$op1144_v3_run} {
    op1144_v3_procs
    puts OP1144_HELPERS_READY
    set failed [catch {op1144_session} message]
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists op1144_scopes]} {
        if {[catch {op1144_audit final 0} detail]} {lappend cleanup $detail}
    }
    if {[catch {op1144_save final-empty.el 1} detail]} {lappend cleanup $detail}
    if {$failed || [llength $cleanup]} {
        puts "OP1144_CAPTURE_FAILED $message cleanup=$cleanup"
    } else {puts OP1144_CAPTURE_DONE_1144}
    gui_exit -noprompt
}

} else {
    puts "OP1144_CAPTURE_FAILED helper-load-gate=$op1144_v3_load_message"
    if {$op1144_v3_run} {gui_exit -noprompt} else {error $op1144_v3_load_message}
}

