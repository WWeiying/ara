# Independent procedure-only successor; all inherited five-stage audits remain.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_batch763.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/native_audit_exactcount764.tcl}
# No native queries removed. Only the repeated name-count scan is replaced.
proc batch_scale_audit {stage} {
    global batch_scale_instances qc_seen
    set index 0
    foreach instance $batch_scale_instances {
        p740_root
        gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
        qc_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set qc_seen {}
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) batch_scale_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $stream "handle\tpath\tmeta\tname\tcolumn1\tcolumn2"
        set failed [catch {qc_walk [gui_list_get -id CovDetail.1 -firstChild] $stream} message]
        close $stream
        if {$failed} {error $message}
        native764_exact_names $qc_seen [lindex $instance 1]
        incr index
    }
}
