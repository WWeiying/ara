# Read-only successor extension; requires the already loaded pmp4_query helper.
# This library is not a session entry point and performs no exclusion operations.
proc pmp4v2_visit {stream item depth} {
    global pmp4v2_seen pmp4v2_count
    while {$item ne "" && $item ne "0"} {
        if {$depth > 32 || $pmp4v2_count >= 256 || [info exists pmp4v2_seen($item)]} {
            error "FSM native tree exceeds bounded unique-row contract"
        }
        set pmp4v2_seen($item) 1
        incr pmp4v2_count
        puts $stream [join [list ROW $item $depth] "\t"]
        foreach property {-path -meta -childCount -depth} {
            pmp4_query $stream PROPERTY [list gui_list_get -id CovDetail.1 $property $item]
        }
        for {set column 0} {$column < 12} {incr column} {
            pmp4_query $stream CELL [list gui_list_get -id CovDetail.1 -text $column $item]
        }
        set child [gui_list_get -id CovDetail.1 -firstChild $item]
        if {$child ne "" && $child ne "0"} {pmp4v2_visit $stream $child [expr {$depth+1}]}
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc pmp4v2_rows {stream} {
    global pmp4v2_seen pmp4v2_count
    pmp4_query $stream SHOW_LIST {gui_covdetail_select -id CovDetail.1 -fsmShow List}
    update
    pmp4_query $stream DUMP_WIDGET {gui_dump_common_list -id CovDetail.1}
    array unset pmp4v2_seen
    set pmp4v2_count 0
    pmp4v2_visit $stream [gui_list_get -id CovDetail.1 -firstChild] 0
    puts $stream [join [list ROW_COUNT $pmp4v2_count] "\t"]
}
