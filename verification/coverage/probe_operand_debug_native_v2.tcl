set probe_library_only 1
source [file join [file dirname [info script]] probe_operand_debug_native.tcl]
rename probe_tree probe_initial_tree
proc probe_tree {stream metric} {
    if {$metric eq "line"} {
        puts "DBG_BLOCK_ACTION_BEGIN"
        set failed [catch {gui_list_action -id CovDetail.1 Block} detail]
        puts "DBG_BLOCK_ACTION_END failed=$failed detail=$detail"
        if {!$failed} {
            puts "DBG_BLOCK_DETAIL_TYPE [gui_covdetail_query -id CovDetail.1 -name type]"
            gui_list_expand -id CovDetail.1 -all {<root>}
        }
        probe_initial_tree $stream $metric
        return
    }
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    set leaves 0
    for {set p 0} {$p < 1000 && $parent ne "" && $parent ne "0"} {incr p} {
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        set child [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$child ne "" && $child ne "0"} {
            incr leaves
            if {$leaves > 4000} {error "Bounded branch diagnostic exhausted"}
            set meta [gui_list_get -id CovDetail.1 -meta $child]
            set path [gui_list_get -id CovDetail.1 -path $child]
            if {![regexp {^(Branch|MISSING_ELSE)([0-9]+)\.([0-9]+)$} $meta]} {
                puts "DBG_FIRST_UNKNOWN parent=$parentpath meta=$meta path=$path scanned_parents=$p scanned_leaves=$leaves"
                probe_row $stream $metric $parent 0
                probe_row $stream $metric $child 1
                return
            }
            set child [gui_list_get -id CovDetail.1 -nextSibling $child]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    error "No unknown native branch leaf found within explicit bound"
}
if {[catch {probe_session} message]} {puts "DBG_PROBE_FAILED $message\n$::errorInfo"}
gui_exit -noprompt
