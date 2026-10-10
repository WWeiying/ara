# Bounded read-only API/identity discovery on the selfchecked standalone VDB.
source $env(LZC_SELECTOR_NATIVE_SELECTION)
if {![string match "lzc_selector_native_*.dut" $lsn_scope]} {error "Standalone only"}
set failed [catch {
    gui_open_cov -hier $lsn_vdb -testdir [list $lsn_vdb] -test [list $lsn_test] -merge LZCSelectorReadOnlyDiscovery
    foreach api {gui_list_get_selected gui_list_get gui_covdetail_query gui_list_select} {help $api}
    gui_list_action -id CoverageTable.1 -column Condition $lsn_scope
    puts "LSN_DISCOVER_ALL_CONDITIONS [list [gui_list_get_selected -id CovDetail.1 -list cond -all -flat]]"
    foreach args {{-list cond -all} {-list cond -all -columns {ID Coverage Condition}}
                  {-list cond -all -columns {0 1 2 3}}} {
        set error [catch {eval gui_list_get_selected -id CovDetail.1 $args} result]
        puts "LSN_DISCOVER_QUERY [list $args] error=$error result=[list $result]"
    }
    set first [lindex [gui_list_get_selected -id CovDetail.1 -list cond -all -flat] 0]
    gui_list_select -id CovDetail.1 -list cond -select [list $first]
    foreach args {{-list vector -all} {-list vector -all -columns {ID Coverage 1 2}}
                  {-list vector -all -columns {0 1 2 3}} {-list vector -all -flat}} {
        set error [catch {eval gui_list_get_selected -id CovDetail.1 $args} result]
        puts "LSN_DISCOVER_VECTOR_QUERY [list $args] error=$error result=[list $result]"
    }
    puts LZC_SELECTOR_NATIVE_DISCOVERY_COMPLETE
} message]
puts "LSN_DISCOVER_STATUS failed=$failed message=[list $message]"
gui_exclusion -reset
gui_exclusion_file -save -file [list [file join $lsn_output discovery-final-empty.el]]
gui_exit -noprompt
