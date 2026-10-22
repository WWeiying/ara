# Procedure-only addition; one population load, immutable original five stages.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_population_union.tcl}
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
        foreach wanted [lindex $instance 1] {
            set count 0
            foreach name $qc_seen {if {$name eq $wanted} {incr count}}
            qc_need [expr {$count == 1}] "Missing/ambiguous scale object $wanted"
        }
        incr index
    }
}
rename combo_audit batch763_original_audit
proc combo_audit {stage mode active} {
    batch763_original_audit $stage $mode $active
    batch_scale_audit $mode
}
