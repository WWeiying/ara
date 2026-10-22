# Discriminating native pilot without speculative widget queries.
set lsn_v2_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_capture_v2.tcl}
source $env(LZC_SELECTOR_NATIVE_SELECTION)
if {![string match "lzc_selector_native_*.dut" $lsn_scope]} {error "Standalone only"}
set failed [catch {
    gui_open_cov -hier $lsn_vdb -testdir [list $lsn_vdb] -test [list $lsn_test] -merge LZCSelectorTernaryNativePilot
    gui_list_action -id CoverageTable.1 -column Condition $lsn_scope
    foreach row $lsn_rows {
        if {[lindex $row 0] eq "cond" && [lindex $row 1] eq "3"} {
            lsn_select cond [lindex $row 3]
            break
        }
    }
    set names [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
    lsn_require [expr {[lsort $names] eq {0 1}}] "Root ternary vector names differ"
    help gui_cov_show_cond_ids
    help gui_dump_common_list
    puts "LSN_DUMP_BEGIN"
    gui_dump_common_list -id CovDetail.1
    puts "LSN_DUMP_END"
    foreach vector {1 0} {
        lsn_select vector $vector
        puts "LSN_TERNARY_BEFORE vector=$vector excluded=[gui_exclusion -id CovDetail.1 -list vector -excluded -selected]"
        gui_exclude_items -id CovDetail.1 -list vector -selected -annotation {Standalone monitored identity native pilot only}
        puts "LSN_TERNARY_EXCLUDE_RETURNED vector=$vector"
        gui_exclusion_file -save -file [list [file join $env(LZC_SELECTOR_NATIVE_DISCOVERY_OUTPUT) "native-$vector.el"]]
        gui_exclusion -reset
    }
    puts LZC_SELECTOR_NATIVE_TERNARY_DISCOVERY_COMPLETE
} message]
puts "LSN_TERNARY_STATUS failed=$failed message=[list $message]"
gui_exclusion -reset
gui_exclusion_file -save -file [list [file join $env(LZC_SELECTOR_NATIVE_DISCOVERY_OUTPUT) final-empty.el]]
gui_exit -noprompt
