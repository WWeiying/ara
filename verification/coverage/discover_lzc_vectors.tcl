# Discover native truth-table row identities, without changing exclusions.
proc lzc_or_expression {level index} {
    return "(gen_lzc.sel_nodes\[(((2 ** ($level + 1)) - 1) + ($index * 2))\] | gen_lzc.sel_nodes\[((((2 ** ($level + 1)) - 1) + ($index * 2)) + 1)\])"
}

proc apply_reviewed_waivers {id} {
    global env
    set scopes [list $env(LZC_DISCOVERY_SCOPE) \
        {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mfpu_a.genblk4.leading_zero_e32}]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native-condition-vectors.csv] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream {Scope Expression NativeNames NativeColumns}
    set count 0
    set failed [catch {
        foreach scope $scopes {
            gui_list_action -id $id -column Condition $scope
            if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Condition"} {
                error "Not Condition view"
            }
            foreach coord {{0 0} {1 1}} {
                set level [lindex $coord 0]
                set index [lindex $coord 1]
                set expression [lzc_or_expression $level $index]
                set old [gui_list_get_selected -id CovDetail.1 -list cond -first]
                if {[llength $old]} {gui_list_select -id CovDetail.1 -list cond -unselect [lindex $old 0]}
                gui_list_select -id CovDetail.1 -list cond -select [list $expression]
                set selected [gui_list_get_selected -id CovDetail.1 -list cond -first]
                puts "LZC_SELECTION expected=[list $expression] returned=[list $selected]"
                set normalized [lindex $selected 0]
                for {set unwrap 0} {$unwrap < 3 && $normalized ne $expression} {incr unwrap} {
                    if {[llength $normalized] != 1} {break}
                    set normalized [lindex $normalized 0]
                }
                if {$normalized ne $expression} {
                    error "Exact expression selection differs: [list $selected]"
                }
                set selected_count [gui_list_get_selected -id CovDetail.1 -list vector -count]
                while {$selected_count > 0} {
                    set first [gui_list_get_selected -id CovDetail.1 -list vector -first]
                    gui_list_select -id CovDetail.1 -list vector -unselect [lindex $first 0]
                    set next_count [gui_list_get_selected -id CovDetail.1 -list vector -count]
                    if {$next_count >= $selected_count} {error "Vector deselection made no progress"}
                    set selected_count $next_count
                }
                # Documented -all/-columns accesses the vector widget; gui_list_get cannot.
                set names [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
                set columns [gui_list_get_selected -id CovDetail.1 -list vector -all -flat -columns {ID Coverage 1 2}]
                csv_row $stream [list $scope $expression $names $columns]
                puts "LZC_VECTOR_DATA names=[list $names] columns=[list $columns]"
                if {[llength $columns] != 3 || [llength $names] != 3} {
                    error "Expected three-row OR matrix: names=[list $names] columns=[list $columns]"
                }
                incr count 3
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "LZC_READ_ONLY_DISCOVERY_DONE $count"
}
