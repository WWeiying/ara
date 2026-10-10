# Tcl 8.4 only. Exact native vector names; IDs are learned from the saved EL.
proc lzc_batch_clear {kind} {
    set count [gui_list_get_selected -id CovDetail.1 -list $kind -count]
    while {$count > 0} {
        set first [gui_list_get_selected -id CovDetail.1 -list $kind -first]
        gui_list_select -id CovDetail.1 -list $kind -unselect [lindex $first 0]
        set next [gui_list_get_selected -id CovDetail.1 -list $kind -count]
        if {$next >= $count} {error "Native deselection did not progress"}
        set count $next
    }
}

proc lzc_batch_select {names} {
    lzc_batch_clear vector
    if {[llength $names]} {gui_list_select -id CovDetail.1 -list vector -select $names}
    if {[gui_list_get_selected -id CovDetail.1 -list vector -count] != [llength $names]} {
        error "Exact vector selection count differs"
    }
    set got [gui_list_get_selected -id CovDetail.1 -list vector -flat]
    if {[lsort $got] ne [lsort $names]} {error "Exact vector names differ"}
}

proc lzc_batch_point {id group} {
    set scope [lindex $group 0]
    set expression [lindex $group 1]
    gui_list_action -id $id -column Condition $scope
    if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Condition"} {error "Not Condition view"}
    lzc_batch_clear cond
    gui_list_select -id CovDetail.1 -list cond -select [list $expression]
    if {[gui_list_get_selected -id CovDetail.1 -list cond -count] != 1} {error "Condition count differs"}
    set selected [lindex [gui_list_get_selected -id CovDetail.1 -list cond -first] 0]
    for {set n 0} {$n < 3 && $selected ne $expression} {incr n} {
        if {[llength $selected] != 1} {break}
        set selected [lindex $selected 0]
    }
    if {$selected ne $expression} {error "Selected expression differs"}
    set names [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
    if {[lsort $names] ne [lsort [lindex $group 2]]} {error "Native truth table differs"}
}

proc lzc_batch_audit {id stream stage active} {
    global lzc_batch_groups
    foreach group $lzc_batch_groups {
        lzc_batch_point $id $group
        set targets [lindex $group 3]
        set retained [lindex $group 4]
        set keep 0
        foreach vector $retained {
            lzc_batch_select [list $vector]
            set state [gui_exclusion -id CovDetail.1 -list vector -excluded -selected]
            if {$state ne "0"} {error "Retained vector excluded/nonboolean state"}
            incr keep $state
        }
        set target 0
        foreach vector $targets {
            lzc_batch_select [list $vector]
            set state [gui_exclusion -id CovDetail.1 -list vector -excluded -selected]
            if {($state ne "0" && $state ne "1") || $state != $active} {
                error "Target exclusion state differs/nonboolean state"
            }
            incr target $state
        }
        csv_row $stream [list $stage [lindex $group 0] [lindex $group 1] \
            [join [lindex $group 2] { }] [join $targets { }] [join $retained { }] $target $keep]
    }
    flush $stream
}

proc apply_reviewed_waivers {id} {
    global env lzc_batch_groups
    set stream ""
    set failed [catch {
        source [file join $env(DVE_COVERAGE_OUTPUT) groups.tcl]
        set total 0
        foreach group $lzc_batch_groups {incr total [llength [lindex $group 3]]}
        if {$total != 180} {error "Exact180 target population required"}
        set stream [open [file join $env(DVE_COVERAGE_OUTPUT) neighbor-audit.csv] w]
        fconfigure $stream -encoding utf-8 -translation lf
        csv_row $stream {Stage Scope Expression NativeNames Targets Retained TargetExcluded RetainedExcluded}
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]]
        lzc_batch_audit $id $stream before 0
        foreach group $lzc_batch_groups {
            set targets [lindex $group 3]
            if {![llength $targets]} {continue}
            lzc_batch_point $id $group
            lzc_batch_select $targets
            gui_exclude_items -id CovDetail.1 -list vector -selected \
                -annotation {LZC padding native format capture only; no application approval}
        }
        gui_exclusion -id $id -recalculate
        lzc_batch_audit $id $stream selected 1
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
        gui_exclusion -reset
        lzc_batch_audit $id $stream reset 0
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) reset-empty.el]]
        gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
        gui_exclusion -id $id -recalculate
        if {[gui_cov_excl_review -isEmpty] != 1} {error "Import requires exclusion review"}
        lzc_batch_audit $id $stream reloaded 1
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) second.el]]
    } message]
    # Cleanup is outside the capture catch, including errors during selection/export.
    set cleanup_errors {}
    if {[catch {gui_exclusion -reset} cleanup_message]} {lappend cleanup_errors $cleanup_message}
    if {$stream ne "" && [info exists lzc_batch_groups]} {
        if {[catch {lzc_batch_audit $id $stream final 0} cleanup_message]} {
            lappend cleanup_errors $cleanup_message
        }
    }
    if {[catch {
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) final-empty.el]]
    } cleanup_message]} {lappend cleanup_errors $cleanup_message}
    if {$stream ne "" && [catch {close $stream} cleanup_message]} {lappend cleanup_errors $cleanup_message}
    if {[llength $cleanup_errors]} {error "Final reset audit failed: $cleanup_errors; capture: $message"}
    if {$failed} {error $message}
    puts "LZC_BATCH_CAPTURE_DONE 180"
}
