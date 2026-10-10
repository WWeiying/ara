# Called by the immutable hierarchy exporter, after its raw summary.
# All own helpers are prefixed; definition errors propagate to exporter catch.
if {[llength [info commands oq_*]] || [llength [info commands apply_reviewed_waivers]]} {
    error "Operand helper command collision"
}
proc oq_require {condition message} {if {!$condition} {error $message}}
proc oq_select {metas} {
    set old [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -list branch -unselect $old}
    if {[llength $metas]} {gui_list_select -id CovDetail.1 -list branch -select $metas}
    set actual [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    oq_require [expr {[lsort $actual] eq [lsort $metas]}] "Operand exact selection differs"
}
proc oq_metadata {id scope {refresh 0}} {
    global oq_keys oq_cached_metadata
    gui_list_action -id $id -column Branch $scope
    oq_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Not Branch view"
    gui_list_expand -id CovDetail.1 -all {<root>}
    if {!$refresh && [info exists oq_cached_metadata($scope)]} {return $oq_cached_metadata($scope)}
    array set found {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        oq_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "Unexpected branch parent"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            oq_require [regexp {^(Branch|MISSING_ELSE)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "Unexpected leaf metadata"
            oq_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta"}] "Leaf/parent identity differs"
            oq_require [expr {[gui_list_get -id CovDetail.1 -childCount $item] == 0}] "Not branch vector leaf"
            set key "$sid,$vid"
            oq_require [expr {![info exists found($key)]}] "Duplicate leaf"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    oq_require [expr {[lsort [array names found]] eq [lsort $oq_keys($scope)]}] "Full XML branch inventory differs"
    if {[info exists oq_cached_metadata($scope)]} {
        array set old $oq_cached_metadata($scope)
        foreach key $oq_keys($scope) {
            oq_require [expr {$old($key) eq $found($key)}] "Fresh metadata differs from initial inventory"
        }
    }
    set oq_cached_metadata($scope) [array get found]
    puts "OQ_INVENTORY $scope full count=[array size found]"
    return [array get found]
}
proc oq_states {id phase active} {
    global oq_scopes oq_keys oq_targets env
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) "states_$phase.tsv"] w]
    puts $stream "scope\tcoordinate\tmeta\tpath\texcluded\tproof"
    foreach scope $oq_scopes {
        array set metadata [oq_metadata $id $scope [expr {$phase eq "before" || $phase eq "reloaded"}]]
        set included {}
        foreach key $oq_keys($scope) {
            set wanted [expr {$active && [lsearch -exact $oq_targets($scope) $key] >= 0}]
            if {!$wanted} {lappend included [lindex $metadata($key) 0]}
        }
        oq_require [expr {[llength $included] > 0}] "No retained group"
        oq_select $included
        oq_require [expr {[gui_exclusion -id CovDetail.1 -list branch -excluded -selected] == 0}] "Retained/reset group contains exclusion"
        puts "OQ_GROUP $phase $scope [llength $included] excluded=0"
        foreach key $oq_keys($scope) {
            set meta [lindex $metadata($key) 0]
            set path [lindex $metadata($key) 1]
            set wanted [expr {$active && [lsearch -exact $oq_targets($scope) $key] >= 0}]
            set proof exact_group_any_zero
            if {$wanted} {
                oq_select [list $meta]
                oq_require [expr {[gui_exclusion -id CovDetail.1 -list branch -excluded -selected] == 1}] "Exact target not excluded"
                set proof singleton
            }
            puts $stream "$scope\t$key\t$meta\t$path\t$wanted\t$proof"
        }
    }
    close $stream
    puts "OQ_STATES $phase"
}
proc oq_callback {stage} {
    global env oq_first_sha
    if {$stage eq "second"} {
        set result [exec python3 -B [file join $env(OPERAND_BUNDLE) operand_runtime.py] --snapshot-sha256 $env(OPERAND_SNAPSHOT_SHA256) --output $env(DVE_COVERAGE_OUTPUT) --session $stage --first-sha256 $oq_first_sha]
    } else {
        set result [exec python3 -B [file join $env(OPERAND_BUNDLE) operand_runtime.py] --snapshot-sha256 $env(OPERAND_SNAPSHOT_SHA256) --output $env(DVE_COVERAGE_OUTPUT) --session $stage]
    }
    puts $result
    if {$stage eq "first"} {
        oq_require [regexp {OQ_FIRST_SHA ([0-9a-f]{64})} $result unused oq_first_sha] "Missing first-export pin"
    }
}
proc oq_save {name} {
    global env
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) $name]]
}
proc oq_summary {id filename} {
    global env seen row_count
    gui_list_expand -id $id -all {<root>}
    set columns {}
    set header {Name Depth}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id $id -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        lappend columns $column
        lappend header $label
    }
    oq_require [expr {[llength $columns] > 0}] "No coverage columns"
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) $filename] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream $header
    array unset seen
    array set seen {}
    set row_count 0
    set failed [catch {export_rows $stream $id "" 0 $columns} message]
    close $stream
    if {$failed} {error $message}
    oq_require [expr {$row_count > 0}] "Empty summary"
}
proc apply_reviewed_waivers {id} {
    global env oq_scopes oq_keys oq_targets oq_observers oq_stage oq_first_sha
    source [file join $env(OPERAND_BUNDLE) selection.tcl]
    puts "OQ_SESSION_ROOT $env(OPERAND_SNAPSHOT_SHA256)"
    puts "OQ_TOOL_TCL [info patchlevel]"
    oq_save initial-empty.el
    oq_callback raw
    oq_states $id before 0
    if {$oq_stage eq "capture"} {
        foreach scope $oq_scopes {
            array set metadata [oq_metadata $id $scope]
            foreach key $oq_targets($scope) {
                oq_select [list [lindex $metadata($key) 0]]
                gui_exclude_items -id CovDetail.1 -list branch -selected -annotation {Operand parameter native discovery; exact vectors only; not application approval}
            }
        }
    } else {
        gui_exclusion_file -load -file [list [file join $env(OPERAND_BUNDLE) union.el]]
        foreach scope $oq_observers {
            gui_exclude_items -id $id -annotation {Verification observer; checker remains active} -recursive [list $scope]
        }
    }
    gui_exclusion -id $id -recalculate
    oq_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Initial selection needs review"
    oq_states $id selected 1
    oq_save first.el
    oq_callback first
    gui_exclusion -reset
    oq_states $id reset 0
    oq_save reset-empty.el
    oq_callback empty
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id $id -recalculate
    oq_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Roundtrip import needs review"
    puts OQ_REVIEW_EMPTY
    oq_states $id reloaded 1
    oq_save second.el
    oq_callback second
    if {$oq_stage eq "report"} {oq_summary $id summary_waived.csv.partial}
    gui_exclusion -reset
    oq_states $id final 0
    oq_save final-empty.el
    oq_callback final
    puts OQ_SESSION_DONE
}
