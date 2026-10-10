# Fresh adapter only. Source after frozen libraries; never edit their definitions on disk.
proc six2_native_selection {value} {
    for {set depth 0} {$depth < 4} {incr depth} {
        if {[llength $value] != 1} {return $value}
        set inner [lindex $value 0]
        if {$inner eq $value} {return $value}
        set value $inner
    }
    error "SIX2 selection wrapper depth exceeds contract"
}
proc six2_dbg_select {metric meta} {
    dbg_require [expr {$metric eq "branch"}] "SIX2 only reviewed branch selections supported"
    dbg_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)[0-9]+\.[0-9]+$} $meta] "SIX2 invalid expected leaf"
    set raw [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    set old [six2_native_selection $raw]
    if {[llength $raw] && ![llength $old]} {
        puts "SIX2_EMPTY_SELECTION_NORMALIZED raw=[list $raw] expected=[list $meta]"
    }
    foreach item $old {
        dbg_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)[0-9]+\.[0-9]+$} $item] "SIX2 unknown nonempty old selection"
    }
    if {[llength $old]} {
        gui_list_select -id CovDetail.1 -list branch -unselect $old
    }
    gui_list_select -id CovDetail.1 -list branch -select [list $meta]
    set actual [six2_native_selection [gui_list_get_selected -id CovDetail.1 -list branch -flat]]
    dbg_require [expr {[llength $actual] == 1 && [lindex $actual 0] eq $meta}] "SIX2 exact singleton readback differs"
}
proc six2_install_selection_adapter {} {
    dbg_require [expr {[llength [info commands dbg_select]] == 1 &&
                       [llength [info commands six2_previous_dbg_select]] == 0}] "SIX2 adapter installation differs"
    rename dbg_select six2_previous_dbg_select
    proc dbg_select {metric meta} {six2_dbg_select $metric $meta}
}
