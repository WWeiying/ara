# Procedure-only successor; preserve the entire frozen745 report and its queue audits.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_combo745.tcl}
proc diagnostic_audit {stage} {
    global diagnostic_instances qc_seen
    set index 0
    foreach instance $diagnostic_instances {
        gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
        qc_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set qc_seen {}
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) diagnostic_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $stream "handle\tpath\tmeta\tname\tcolumn1\tcolumn2"
        set failed [catch {qc_walk [gui_list_get -id CovDetail.1 -firstChild] $stream} message]
        close $stream
        if {$failed} {error $message}
        foreach wanted [lindex $instance 1] {
            set count 0
            foreach name $qc_seen {if {$name eq $wanted} {incr count}}
            qc_need [expr {$count == 1}] "Missing/ambiguous diagnostic object $wanted"
        }
        incr index
    }
}
rename combo_audit diagnostic745_original_audit
proc combo_audit {stage mode active} {
    diagnostic745_original_audit $stage $mode $active
    p740_root
    diagnostic_audit $mode
}
