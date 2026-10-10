# Exact full-scope selection, never child rooted percentage/name qualification.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_batch768_v2.tcl}
proc observer766_audit {stage} {
    foreach group $::observer766_groups {
        p740_root
        p740_select [lindex $group 0]
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
