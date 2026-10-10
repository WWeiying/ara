# Exact two-bank Condition discovery. IDs-display output is observation, not mapping.
proc qbf_require {ok message} {if {!$ok} {error $message}}
proc qbf_name {value} {
    for {set i 0} {$i < 4 && [llength $value] == 1} {incr i} {
        set next [lindex $value 0]
        if {$next eq $value} {break}
        set value $next
    }
    return $value
}
proc qbf_emit {values} {
    global qbf_stream
    puts $qbf_stream $values
    flush $qbf_stream
}
proc qbf_clear {} {
    set raw [gui_list_get_selected -id CovDetail.1 -list cond -flat]
    foreach token $raw {
        set name [qbf_name $token]
        if {$name ne ""} {gui_list_select -id CovDetail.1 -list cond -unselect [list $name]}
    }
    set remaining [gui_list_get_selected -id CovDetail.1 -list cond -flat]
    foreach token $remaining {qbf_require [expr {[qbf_name $token] eq ""}] "Nonempty previous selection"}
}
proc qbf_children {handle depth parent_path parent_meta expected} {
    global qbf_seen qbf_nodes qbf_matches
    qbf_require [expr {$depth <= 8 && $qbf_nodes < 128 && ![info exists qbf_seen($handle)]}] "Child bound/cycle"
    set qbf_seen($handle) 1
    incr qbf_nodes
    set path [gui_list_get -id CovDetail.1 -path $handle]
    set meta [gui_list_get -id CovDetail.1 -meta $handle]
    if {$depth > 0 && $path eq "$parent_path.$expected" && $meta eq "$parent_meta  .$expected"} {
        lappend qbf_matches [list $handle $path $meta]
    }
    set child [gui_list_get -id CovDetail.1 -firstChild $handle]
    while {$child ne "" && $child ne "0"} {
        qbf_children $child [expr {$depth + 1}] $parent_path $parent_meta $expected
        set child [gui_list_get -id CovDetail.1 -nextSibling $child]
    }
}
proc qbf_scope {scope groups} {
    global qbf_seen qbf_nodes qbf_matches
    qbf_require [expr {$scope eq "ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank0.i_payload_buffer" ||
        $scope eq "ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank1.i_payload_buffer"}] "Exact payload banks only"
    qbf_require [expr {[llength $groups] == 672}] "Exact per-bank group population"
    gui_cov_show_cond_ids -show 0
    gui_list_action -id CoverageTable.1 -column Condition $scope
    qbf_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Condition"}] "Wrong view"
    gui_list_expand -id CovDetail.1 -all {<root>}
    qbf_clear
    array set roots {}
    array set seen {}
    set n 0
    set handle [gui_list_get -id CovDetail.1 -firstChild]
    while {$handle ne "" && $handle ne "0"} {
        qbf_require [expr {$n < 8192 && ![info exists seen($handle)]}] "Root bound/cycle"
        set seen($handle) 1
        incr n
        set meta [gui_list_get -id CovDetail.1 -meta $handle]
        qbf_require [expr {![info exists roots($meta)]}] "Ambiguous native root meta"
        set roots($meta) $handle
        set handle [gui_list_get -id CovDetail.1 -nextSibling $handle]
    }
    qbf_emit [list inventory $scope $n [gui_list_get_selected -id CovDetail.1 -list cond -all -flat]]
    set nested 0
    foreach group $groups {
        qbf_require [expr {[llength $group] == 3}] "Group tuple shape"
        set expression [lindex $group 0]
        set parent [lindex $group 1]
        set expected [lindex $group 2]
        if {$parent eq ""} {
            qbf_require [expr {[info exists roots($expression)]}] "Actual top group absent"
            set handle $roots($expression)
            set path [gui_list_get -id CovDetail.1 -path $handle]
            set meta [gui_list_get -id CovDetail.1 -meta $handle]
        } else {
            incr nested
            qbf_require [expr {[info exists roots($parent)]}] "Actual parent absent"
            set parent_handle $roots($parent)
            set parent_path [gui_list_get -id CovDetail.1 -path $parent_handle]
            set parent_meta [gui_list_get -id CovDetail.1 -meta $parent_handle]
            catch {unset qbf_seen}
            array set qbf_seen {}
            set qbf_nodes 0
            set qbf_matches {}
            qbf_children $parent_handle 0 $parent_path $parent_meta $expression
            qbf_require [expr {[llength $qbf_matches] == 1}] "Missing/ambiguous actual child"
            set object [lindex $qbf_matches 0]
            set handle [lindex $object 0]
            set path [lindex $object 1]
            set meta [lindex $object 2]
        }
        qbf_emit [list object $scope $expression $parent $handle $path $meta]
        qbf_clear
        # Use the observed meta only, never a constructed selector or XML number.
        gui_list_select -id CovDetail.1 -list cond -select [list $meta]
        set selected [gui_list_get_selected -id CovDetail.1 -list cond -flat]
        qbf_require [expr {[gui_list_get_selected -id CovDetail.1 -list cond -count] == 1 && [qbf_name $selected] eq $meta}] "Actual object selection mismatch"
        set raw [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
        set names {}
        foreach token $raw {lappend names [qbf_name $token]}
        qbf_require [expr {[llength $names] <= 3 && [lsort $names] eq [lsort $expected]}] "Actual truth table mismatch"
        gui_cov_show_cond_ids -show 1
        set id_display [gui_list_get_selected -id CovDetail.1 -list cond -flat]
        set vector_display [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
        gui_cov_show_cond_ids -show 0
        qbf_require [expr {[qbf_name [gui_list_get_selected -id CovDetail.1 -list cond -flat]] eq $meta}] "ID display changed selected object"
        qbf_emit [list group $scope $expression $parent $handle $path $meta $selected $raw $id_display $vector_display]
    }
    qbf_clear
    qbf_require [expr {$nested == 224}] "Exact nested group population"
    qbf_emit [list scope_complete $scope 672 224]
}
