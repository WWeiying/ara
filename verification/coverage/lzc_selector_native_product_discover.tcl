# Read-only product discovery. No exclusion API, callbacks, or helper sourcing.
proc lpd_require {ok message} {if {!$ok} {error $message}}
proc lpd_normalize {value} {
    for {set depth 0} {$depth < 4 && [llength $value] == 1} {incr depth} {
        set next [lindex $value 0]
        if {$next eq $value} {break}
        set value $next
    }
    return $value
}
proc lpd_clear {listname} {
    set n [gui_list_get_selected -id CovDetail.1 -list $listname -count]
    for {set tries 0} {$n > 0 && $tries < 256} {incr tries} {
        set old [lpd_normalize [gui_list_get_selected -id CovDetail.1 -list $listname -first]]
        gui_list_select -id CovDetail.1 -list $listname -unselect [list $old]
        set after [gui_list_get_selected -id CovDetail.1 -list $listname -count]
        lpd_require [expr {$after < $n}] "Selection clearing did not progress"
        set n $after
    }
    lpd_require [expr {$n == 0}] "Selection clearing bound exceeded"
}
proc lpd_select {listname name} {
    lpd_clear $listname
    gui_list_select -id CovDetail.1 -list $listname -select [list $name]
    lpd_require [expr {[gui_list_get_selected -id CovDetail.1 -list $listname -count] == 1 &&
        [lpd_normalize [gui_list_get_selected -id CovDetail.1 -list $listname -flat]] eq $name}] "Exact native selection differs"
}
proc lpd_emit {values} {
    global lpd_stream
    puts $lpd_stream $values
    flush $lpd_stream
}
proc lpd_branch {scope} {
    gui_list_action -id CoverageTable.1 -column Branch $scope
    lpd_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Not Branch detail"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set seen {}
    set rows 0
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        lpd_require [expr {![info exists seen($parent)] && $rows < 256}] "Branch traversal bound/cycle"
        set seen($parent) 1
        set path [gui_list_get -id CovDetail.1 -path $parent]
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            lpd_require [expr {![info exists seen($item)] && $rows < 256}] "Branch leaf traversal bound/cycle"
            set seen($item) 1
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            lpd_require [regexp {^Branch([0-9]+)\.([0-9]+)$} $meta unused id arm] "Unexpected native branch meta"
            lpd_require [expr {$path eq "Item$id" && [gui_list_get -id CovDetail.1 -childCount $item] == 0}] "Branch native parent differs"
            lpd_select branch $meta
            lpd_emit [list branch $scope $id $arm $path $meta \
                [gui_list_get_selected -id CovDetail.1 -list branch -flat -columns {ID Coverage}]]
            incr rows
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    lpd_require [expr {$rows > 0}] "Empty native branch inventory"
    return $rows
}
proc lpd_conditions {scope expected} {
    gui_cov_show_cond_ids -show 0
    gui_list_action -id CoverageTable.1 -column Condition $scope
    lpd_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Condition"}] "Not Condition detail"
    lpd_clear cond
    set raw [gui_list_get_selected -id CovDetail.1 -list cond -all -flat]
    set actual {}
    foreach value $raw {lappend actual [lpd_normalize $value]}
    lpd_require [expr {[lsort $actual] eq [lsort $expected]}] "Complete native expression inventory differs"
    lpd_emit [list conditions $scope $raw]
    set rows 0
    foreach expression $actual {
        lpd_select cond $expression
        set names [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
        lpd_require [expr {[llength $names] > 0 && [llength $names] <= 16}] "Native vector inventory bound"
        set cols [gui_list_get_selected -id CovDetail.1 -list vector -all -flat -columns {ID Coverage 1 2}]
        lpd_emit [list condition $scope $expression $names $cols \
            [gui_list_get_selected -id CovDetail.1 -list cond -flat -columns {ID Condition Coverage}]]
        incr rows [llength $names]
    }
    lpd_clear cond
    gui_cov_show_cond_ids -show 1
    lpd_emit [list condition_ids_display $scope \
        [gui_list_get_selected -id CovDetail.1 -list cond -all -flat] \
        [gui_list_get_selected -id CovDetail.1 -list cond -all -flat -columns {ID Condition Coverage}]]
    gui_cov_show_cond_ids -show 0
    return $rows
}
proc lpd_session {} {
    global env lpd_stream lpd_design lpd_testdirs lpd_tests lpd_children
    source $env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION)
    lpd_require [expr {[llength $lpd_tests] == 707 && [llength $lpd_children] == 36}] "Exact approved population required"
    set lpd_stream [open [file join $env(LZC_SELECTOR_NATIVE_PRODUCT_OUTPUT) native-inventory.tcllist] w]
    gui_open_cov -hier $lpd_design -testdir $lpd_testdirs -test $lpd_tests -merge LZC707ProductReadOnlyDiscovery
    lpd_emit [list population $lpd_design $lpd_testdirs $lpd_tests]
    foreach child $lpd_children {
        set scope [lindex $child 0]
        lpd_require [expr {[lindex $child 1] eq "3250293308"}] "Product module checksum binding differs"
        lpd_emit [list child_binding $scope [lindex $child 1] [lindex $child 2]]
        set branches [lpd_branch $scope]
        set vectors [lpd_conditions $scope [lindex $child 3]]
        lpd_emit [list child_complete $scope $branches $vectors]
        puts "LZC_PRODUCT_READONLY_CHILD_COMPLETE $scope branch=$branches vector=$vectors"
    }
    close $lpd_stream
    puts LZC_PRODUCT_READONLY_DISCOVERY_COMPLETE
}
if {![info exists lpd_test_only]} {
    set failed [catch {lpd_session} message]
    if {[info exists lpd_stream]} {catch {close $lpd_stream}}
    if {$failed} {puts "LZC_PRODUCT_READONLY_DISCOVERY_FAILED $message\n$::errorInfo"}
    gui_exit -noprompt
}
