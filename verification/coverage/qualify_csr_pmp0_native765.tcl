# Local settled PMP0 q/next only; existing proven selection/reset lifecycle.
set ::qfp_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/queue_fp_temporaries_native.tcl}
proc qfp_bind {stage instance} {
    global fma_names fma_rows fma_seen env
    set fma_names [lindex $instance 1]; set fma_rows {}; set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    qfp_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native_${stage}_0.tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    qfp_need [expr {[llength $fma_rows] == 770}] "Not exact770 internal targets"
    foreach name $fma_names {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        qfp_need [expr {$count == 1}] "Missing/ambiguous internal target: $name"
    }
    puts [exec $::fma_python -B $::fma_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage --index 0]
    return $fma_rows
}
# Change only the frozen generic session's local label/merge and completion marker.
proc qfp_session {} [string map [list QueueFPU0NativeOnly PMP0InternalNativeOnly \
    {Frozen FPU0 queue whole temporary, settled source constant only} \
    {PMP0 internal q/next constant after valid reset and settled evaluation; no initial-X waiver} \
    QUEUE_FP_TEMP_NATIVE_DONE PMP0_NATIVE_DONE] [info body qfp_session]]
if {![info exists ::pmp_test_only]} {
    if {[catch {qfp_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message; puts $stream $::errorInfo; close $stream
        puts "PMP0_NATIVE_FAILED $message"
        catch {qfp_reset; fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
