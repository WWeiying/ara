# Reuse frozen session order/imports, but do not run the v1 entry.
set ::bg_test_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qbs_bank1_group_hit_native791.tcl}]
proc bg_walk {item stream} {
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        puts $stream [join [list $item $path $meta $name] "\t"]
        bg_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc bg_inventory {stage} {
    set index 0
    foreach scope $::bg_scopes {
        p740_root
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        dw_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Foreign metric"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $f "handle\tpath\tmeta\tname"
        set failed [catch {bg_walk [gui_list_get -id CovDetail.1 -firstChild] $f} detail]
        close $f
        if {$failed} {error $detail}
        puts [bg_call inventory --stage $stage --index $index]
        incr index
    }
}
if {![info exists ::bg_v2_test_only]} {
    set failed [catch {bg_session} detail]
    if {$failed} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f "$detail\n$::errorInfo"; close $f
        puts "QBS_BANK1_GROUP_HIT_V2_NATIVE_FAILED $detail"
    }
    set cleanup [catch {dw_reset; dw_save cleanup-empty.el 1} detail]
    if {$cleanup} {puts "QBS_BANK1_GROUP_HIT_V2_NATIVE_FAILED cleanup $detail"}
    if {!$failed && !$cleanup} {puts QBS_BANK1_GROUP_HIT_V2_NATIVE_DONE}
    gui_exit -noprompt
}
