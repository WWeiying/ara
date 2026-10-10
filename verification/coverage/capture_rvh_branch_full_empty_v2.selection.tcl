# Tcl 8.4. Only exact empty flat-selection tokens are ignored.
proc rvh2_selection {raw} {
    set kept {}
    foreach token $raw {
        if {$token eq ""} {continue}
        dbg_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)[0-9]+\.[0-9]+$} $token] "RVH2 invalid nonempty native selection"
        lappend kept $token
    }
    dbg_require [expr {[llength [lsort -unique $kept]] == [llength $kept]}] "RVH2 duplicate native selection"
    return $kept
}
proc rvh2_dbg_select {metric meta} {
    dbg_require [expr {$metric eq "branch"}] "RVH2 Branch only"
    dbg_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)[0-9]+\.[0-9]+$} $meta] "RVH2 invalid desired leaf"
    set raw [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    puts "RVH2_SELECTION_BEFORE raw=[list $raw] desired=[list $meta]"
    set old [rvh2_selection $raw]
    puts "RVH2_SELECTION_FILTERED old=[list $old] removed=[expr {[llength $raw]-[llength $old]}]"
    if {[llength $old]} {gui_list_select -id CovDetail.1 -list branch -unselect $old}
    gui_list_select -id CovDetail.1 -list branch -select [list $meta]
    set raw [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    puts "RVH2_SELECTION_AFTER raw=[list $raw] desired=[list $meta]"
    set actual [rvh2_selection $raw]
    dbg_require [expr {[llength $actual] == 1 && [lindex $actual 0] eq $meta}] "RVH2 exact singleton readback differs"
}
dbg_require [expr {[llength [info commands dbg_select]] == 1 && [llength [info commands rvh2_original_dbg_select]] == 0}] "RVH2 installation differs"
rename dbg_select rvh2_original_dbg_select
proc dbg_select {metric meta} {rvh2_dbg_select $metric $meta}
