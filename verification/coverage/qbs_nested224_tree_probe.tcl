# Minimal read-only diagnostic body for two bank0 parents. No launcher here.
# Caller supplies qnt_scope, qnt_parents and an open qnt_stream after pinned VDB open.
proc qnt_require {ok message} {if {!$ok} {error $message}}
proc qnt_walk {handle depth} {
    global qnt_stream qnt_seen qnt_nodes
    qnt_require [expr {$depth <= 8 && $qnt_nodes < 128 && ![info exists qnt_seen($handle)]}] "Child tree bound/cycle"
    set qnt_seen($handle) 1
    incr qnt_nodes
    puts $qnt_stream [list child $depth $handle [gui_list_get -id CovDetail.1 -path $handle] [gui_list_get -id CovDetail.1 -meta $handle] [gui_list_get -id CovDetail.1 -childCount $handle]]
    flush $qnt_stream
    set child [gui_list_get -id CovDetail.1 -firstChild $handle]
    while {$child ne "" && $child ne "0"} {
        qnt_walk $child [expr {$depth + 1}]
        set child [gui_list_get -id CovDetail.1 -nextSibling $child]
    }
}
proc qnt_probe {} {
    global qnt_scope qnt_parents qnt_stream qnt_seen qnt_nodes
    qnt_require [expr {$qnt_scope eq "ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank0.i_payload_buffer"}] "Exact observed bank0 scope required"
    qnt_require [expr {[llength $qnt_parents] == 2}] "Two exact diagnostic parents required"
    gui_cov_show_cond_ids -show 0
    gui_list_action -id CoverageTable.1 -column Condition $qnt_scope
    qnt_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Condition"}] "Wrong view"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set roots {}
    array set found {}
    set count 0
    set handle [gui_list_get -id CovDetail.1 -firstChild]
    while {$handle ne "" && $handle ne "0"} {
        qnt_require [expr {$count < 8192 && ![info exists roots($handle)]}] "Root bound/cycle"
        set roots($handle) 1
        incr count
        set meta [gui_list_get -id CovDetail.1 -meta $handle]
        if {[lsearch -exact $qnt_parents $meta] >= 0} {
            qnt_require [expr {![info exists found($meta)]}] "Duplicate actual parent"
            set found($meta) $handle
        }
        set handle [gui_list_get -id CovDetail.1 -nextSibling $handle]
    }
    foreach parent $qnt_parents {
        qnt_require [expr {[info exists found($parent)]}] "Actual parent tree absent"
        set handle $found($parent)
        puts $qnt_stream [list parent $parent $handle [gui_list_get -id CovDetail.1 -path $handle]]
        flush $qnt_stream
        catch {unset qnt_seen}
        array set qnt_seen {}
        set qnt_nodes 0
        qnt_walk $handle 0
        qnt_require [expr {$qnt_nodes > 1}] "No actual nested child returned"
    }
    puts $qnt_stream [list diagnostic_complete NATIVE_IDENTITY_HOLD]
    flush $qnt_stream
}
