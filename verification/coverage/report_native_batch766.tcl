# Independent full766 observer readback, all inherited native audits retained.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_batch764.tcl}
proc observer766_walk {item stream} {
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        dw_select $path $meta
        set excluded [gui_exclusion -id CovDetail.1 -excluded -selected]
        if {$excluded ne "0" && $excluded ne "1"} {error "Observer exclusion not Boolean"}
        puts $stream [join [list $item $path $meta $name $excluded] "\t"]
        observer766_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc observer766_audit {stage} {
    foreach group $::observer766_groups {
        p740_root
        gui_list_action -id CoverageTable.1 -column Toggle [lindex $group 0]
        if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Toggle"} {error "Observer metric differs"}
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) observer766_${stage}_[lindex $group 1].tsv] {WRONLY CREAT EXCL}]
        puts $stream "handle\tpath\tmeta\tname\texcluded"
        set failed [catch {observer766_walk [gui_list_get -id CovDetail.1 -firstChild] $stream} message]
        close $stream
        if {$failed} {error $message}
    }
}
rename combo_audit observer766_original_audit
proc combo_audit {stage mode active} {
    observer766_original_audit $stage $mode $active
    observer766_audit $mode
}
