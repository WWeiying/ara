# Static-prepared only. No launcher is provided or authorized in this tool.
set ::read108_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_requester_read108_native.tcl}
proc qfp_bind {stage instance} {
    global fma_names fma_rows fma_seen env
    set fma_names [lindex $instance 1];set fma_rows {};set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    qfp_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 3].tsv] w]
    puts $stream "handle\tpath\tmeta\tname\texcluded"
    set failed [catch {read108_walk [gui_list_get -id CovDetail.1 -firstChild] $stream} message]
    close $stream
    if {$failed} {error $message}
    qfp_need [expr {[llength $fma_seen] == [lindex $instance 5] && [llength $fma_rows] == [lindex $instance 4]}] "Exact full68/target count"
    puts [exec $::fma_python -B $::fma_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage --index [lindex $instance 3]]
    return $fma_rows
}
proc qfp_session {} [string map [list RequesterRead108NativeOnly QueueFP312NativeOnly \
    {Frozen nine read payloads wdata/be/wen zero after valid reset and settled evaluation; no initial-X waiver} \
    {Frozen global queue FP temporaries: FPU0 globals or unconditional global fp8 zero; settled known controls only, no initial-X waiver} \
    REQUESTER_READ108_NATIVE_DONE QUEUE_FP312_NATIVE_DONE] [info body qfp_session]]
if {![info exists ::qfp312_test_only]} {
    if {[catch {
        qfp_need [expr {[info exists ::env(QFP312_PARENT_LAUNCH_APPROVED)] &&
            $::env(QFP312_PARENT_LAUNCH_APPROVED) eq "EXACT312_FULL68_PARENT_APPROVED"}] "Static prepare only; parent launch not approved"
        qfp_session
    } message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message;puts $stream $::errorInfo;close $stream
        puts "QUEUE_FP312_NATIVE_FAILED $message"
        catch {qfp_reset;fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
