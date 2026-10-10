# One native top-level ternary pilot: discover which monitored ID DVE saves.
set lsn_v2_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_capture_v2.tcl}
source $env(LZC_SELECTOR_NATIVE_SELECTION)
if {![string match "lzc_selector_native_*.dut" $lsn_scope]} {error "Standalone only"}
set failed [catch {
    gui_open_cov -hier $lsn_vdb -testdir [list $lsn_vdb] -test [list $lsn_test] -merge LZCSelectorTernaryDiscovery
    foreach api {gui_list_action gui_list_get_value gui_list_get_meta gui_dump_common_list gui_covdetail_query} {help $api}
    gui_list_action -id CoverageTable.1 -column Condition $lsn_scope
    set found 0
    foreach row $lsn_rows {
        if {[lindex $row 0] eq "cond" && [lindex $row 1] eq "3"} {
            lsn_select cond [lindex $row 3]
            set found 1
            break
        }
    }
    if {!$found} {error "Missing compiled root ternary"}
    puts "LSN_TERNARY_NAMES [list [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]]"
    foreach args {{-list vector -all} {-list vector -all -columns {ID Coverage 1 2}}
                  {-list vector -all -columns {0 1 2 3}}} {
        set error [catch {eval gui_list_get_selected -id CovDetail.1 $args} result]
        puts "LSN_TERNARY_QUERY [list $args] error=$error result=[list $result]"
    }
    foreach listname {expr expression operand subcond} {
        set error [catch {gui_list_get_selected -id CovDetail.1 -list $listname -all -flat} result]
        puts "LSN_TERNARY_LIST $listname error=$error result=[list $result]"
    }
    foreach vector [gui_list_get_selected -id CovDetail.1 -list vector -all -flat] {
        lsn_select vector $vector
        puts "LSN_TERNARY_BEFORE vector=$vector excluded=[gui_exclusion -id CovDetail.1 -list vector -excluded -selected]"
        gui_exclude_items -id CovDetail.1 -list vector -selected -annotation {Standalone native monitored identity discovery only}
        gui_exclusion_file -save -file [list [file join $env(LZC_SELECTOR_NATIVE_DISCOVERY_OUTPUT) "native-$vector.el"]]
        gui_exclusion -reset
    }
    puts LZC_SELECTOR_NATIVE_TERNARY_DISCOVERY_COMPLETE
} message]
puts "LSN_TERNARY_STATUS failed=$failed message=[list $message]"
gui_exclusion -reset
gui_exclusion_file -save -file [list [file join $env(LZC_SELECTOR_NATIVE_DISCOVERY_OUTPUT) final-empty.el]]
gui_exit -noprompt
