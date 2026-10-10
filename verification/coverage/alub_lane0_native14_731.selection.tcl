# Tcl 8.4; discover actual leaf metadata before any singleton exclusion.
proc alub14_selection {metric raw} {
    set kept {}
    foreach token $raw {
        if {$token eq ""} {continue}
        if {$metric eq "line"} {set pattern {^Block[0-9]+$}} else {
            dbg_require [expr {$metric eq "branch"}] "Unsupported metric"
            set pattern {^(Branch|MISSING_ELSE)[0-9]+\.[0-9]+$}
        }
        dbg_require [regexp $pattern $token] "Invalid nonempty actual selection"
        lappend kept $token
    }
    dbg_require [expr {[llength [lsort -unique $kept]] == [llength $kept]}] "Duplicate actual selection"
    return $kept
}
proc dbg_select {metric meta} {
    dbg_require [expr {[alub14_selection $metric [list $meta]] eq [list $meta]}] "Invalid desired actual leaf"
    set options [dbg_options $metric]
    set raw [eval gui_list_get_selected -id CovDetail.1 $options -flat]
    set old [alub14_selection $metric $raw]
    puts "ALUB14_SELECTION raw=[list $raw] filtered=[list $old] desired=[list $meta]"
    if {[llength $old]} {eval gui_list_select -id CovDetail.1 $options -unselect [list $old]}
    eval gui_list_select -id CovDetail.1 $options -select [list [list $meta]]
    set actual [alub14_selection $metric [eval gui_list_get_selected -id CovDetail.1 $options -flat]]
    dbg_require [expr {[llength $actual] == 1 && [lindex $actual 0] eq $meta}] "Singleton actual readback differs"
}
proc dbg_visit_line {item} {
    global dbg_line_found dbg_line_seen
    while {$item ne "" && $item ne "0"} {
        dbg_require [expr {![info exists dbg_line_seen($item)]}] "Native tree cycle"
        set dbg_line_seen($item) 1
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set path [gui_list_get -id CovDetail.1 -path $item]
        set child [gui_list_get -id CovDetail.1 -firstChild $item]
        puts "ALUB14_LINE_ACTUAL handle=[list $item] meta=[list $meta] path=[list $path] child=[list $child]"
        if {[regexp {^Block([0-9]+)$} $meta unused key]} {
            dbg_require [expr {[gui_list_get -id CovDetail.1 -childCount $item] == 0 && ($child eq "" || $child eq "0")}] "Block is not leaf"
            dbg_require [expr {![info exists dbg_line_found($key)]}] "Duplicate native Block"
            dbg_require [regexp "(^|\\.)$meta\$" $path] "Actual Block path differs"
            set dbg_line_found($key) [list $meta $path]
        } elseif {$child ne "" && $child ne "0"} {dbg_visit_line $child}
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
# Preserve established complete discovery; add one readonly category drilldown probe.
rename dbg_metadata alub14_original_metadata
proc dbg_metadata {scope metric} {
    if {$metric eq "line"} {
        gui_list_action -id CoverageTable.1 -column Line $scope
        dbg_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Line"}] "Wrong Line view"
        set item [gui_list_get -id CovDetail.1 -firstChild]
        if {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            puts "ALUB14_LINE_VIEW actualmeta=[list $meta]"
            if {$meta eq "Block"} {
                # Observed category exists; action value is exploratory, not identity proof.
                puts "ALUB14_LINE_BLOCK_PROBE_UNQUALIFIED"
                gui_list_action -id CovDetail.1 -column Category Block
                gui_list_expand -id CovDetail.1 -all {<root>}
                global dbg_line_found dbg_line_seen dbg_keys
                array unset dbg_line_found
                array unset dbg_line_seen
                array set dbg_line_found {}
                array set dbg_line_seen {}
                dbg_visit_line [gui_list_get -id CovDetail.1 -firstChild]
                dbg_require [expr {[lsort [array names dbg_line_found]] eq [lsort $dbg_keys($scope|line)]}] "HOLD: actual complete Block leaves unavailable"
                return [array get dbg_line_found]
            }
        }
    }
    return [alub14_original_metadata $scope $metric]
}
# Adapt only the fixed annotation in the existing audited session body.
set alub14_body [info body dbg_session]
set alub14_old {Reviewed operand debug instrumentation; native qualification only; not aggregate approval}
dbg_require [expr {[string first $alub14_old $alub14_body] >= 0}] "Missing session annotation"
set alub14_source {source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]}
dbg_require [expr {[string first $alub14_source $alub14_body] >= 0}] "Missing session setup"
set alub14_body [string map [list $alub14_source {} $alub14_old {ALUB lane0 static14 native singleton qualification only; not application approval}] $alub14_body]
proc dbg_session {} $alub14_body
