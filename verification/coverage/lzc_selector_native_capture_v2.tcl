# Standalone capture successor. Original pinned helper is loaded read-only.
set lsn_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_capture.tcl}
proc lsn_select {listname name} {
    set n [gui_list_get_selected -id CovDetail.1 -list $listname -count]
    while {$n > 0} {
        set old [gui_list_get_selected -id CovDetail.1 -list $listname -first]
        gui_list_select -id CovDetail.1 -list $listname -unselect [lindex $old 0]
        set after [gui_list_get_selected -id CovDetail.1 -list $listname -count]
        lsn_require [expr {$after < $n}] "Selection clearing did not progress"
        set n $after
    }
    gui_list_select -id CovDetail.1 -list $listname -select [list $name]
    set got [gui_list_get_selected -id CovDetail.1 -list $listname -flat]
    set count [gui_list_get_selected -id CovDetail.1 -list $listname -count]
    puts "LSN_SELECTION list=$listname expected=[list $name] returned=[list $got] count=$count"
    lsn_require [expr {$count == 1}] "Selection is not a singleton"
    for {set depth 0} {$depth < 4 && $got ne $name} {incr depth} {
        if {[llength $got] != 1} {break}
        set got [lindex $got 0]
    }
    lsn_require [expr {$got eq $name}] "Singleton identity differs after exact list normalization"
}
if {![info exists lsn_v2_test_only]} {
    set failed [catch {lsn_session} message]
    if {$failed} {puts "LSN_V2_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists lsn_rows]} {
        if {[catch {lsn_audit final -1} detail]} {lappend cleanup $detail}
        if {[catch {lsn_save final-empty.el 1} detail]} {lappend cleanup $detail}
    }
    if {$failed || [llength $cleanup]} {
        puts "LZC_SELECTOR_NATIVE_FAILED $message cleanup=$cleanup"
    } else {puts LZC_SELECTOR_NATIVE_CAPTURE_COMPLETE_PENDING_SEMANTIC_REVIEW}
    gui_exit -noprompt
}
