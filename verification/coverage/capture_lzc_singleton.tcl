# Exact one-vector native format pilot. Always reset before leaving DVE.
proc lzc_single_select {names} {
    set remaining [gui_list_get_selected -id CovDetail.1 -list vector -count]
    while {$remaining > 0} {
        set old [gui_list_get_selected -id CovDetail.1 -list vector -first]
        gui_list_select -id CovDetail.1 -list vector -unselect [lindex $old 0]
        set after [gui_list_get_selected -id CovDetail.1 -list vector -count]
        if {$after >= $remaining} {error "Native deselection did not progress"}
        set remaining $after
    }
    if {[llength $names]} {gui_list_select -id CovDetail.1 -list vector -select $names}
    if {[gui_list_get_selected -id CovDetail.1 -list vector -count] != [llength $names]} {
        error "Exact vector selection count differs"
    }
    set got [gui_list_get_selected -id CovDetail.1 -list vector -flat]
    if {[lsort $got] ne [lsort $names]} {error "Exact vector names differ"}
}

proc lzc_single_states {stage active} {
    global env
    lzc_single_select {00 10}
    if {[gui_exclusion -id CovDetail.1 -list vector -excluded -selected] != 0} {
        error "Retained vectors excluded"
    }
    lzc_single_select {01}
    if {[gui_exclusion -id CovDetail.1 -list vector -excluded -selected] != $active} {
        error "Target exclusion state differs"
    }
    puts "LZC_SINGLE_STATE $stage retained=0 target=$active"
}

proc apply_reviewed_waivers {id} {
    global env
    help gui_exclude_items
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]]
    gui_list_action -id $id -column Condition $env(LZC_DISCOVERY_SCOPE)
    # WIDTH10 (level=1,index=1): left has in_tmp[8:9], right is constant zero.
    set expression {(gen_lzc.sel_nodes[(((2 ** (1 + 1)) - 1) + (1 * 2))] | gen_lzc.sel_nodes[((((2 ** (1 + 1)) - 1) + (1 * 2)) + 1)])}
    set old [gui_list_get_selected -id CovDetail.1 -list cond -first]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -list cond -unselect [lindex $old 0]}
    gui_list_select -id CovDetail.1 -list cond -select [list $expression]
    set selected [lindex [gui_list_get_selected -id CovDetail.1 -list cond -first] 0]
    for {set n 0} {$n < 3 && $selected ne $expression} {incr n} {
        if {[llength $selected] != 1} {break}
        set selected [lindex $selected 0]
    }
    if {$selected ne $expression} {error "Selected expression differs"}
    set rows [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
    if {[lsort $rows] ne {00 01 10}} {error "Native OR table differs"}
    set failed [catch {
        lzc_single_states before 0
        lzc_single_select {01}
        gui_exclude_items -id CovDetail.1 -list vector -selected \
            -annotation {LZC padding pilot: right child constant zero; native capture only}
        gui_exclusion -id $id -recalculate
        lzc_single_states selected 1
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
        gui_exclusion -reset
        lzc_single_states reset 0
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) reset-empty.el]]
        gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
        gui_exclusion -id $id -recalculate
        if {[gui_cov_excl_review -isEmpty] != 1} {error "Import requires exclusion review"}
        lzc_single_states reloaded 1
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) second.el]]
    } message]
    gui_exclusion -reset
    lzc_single_states final 0
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) final-empty.el]]
    if {$failed} {error $message}
    puts "LZC_READ_ONLY_DISCOVERY_DONE 1"
}
