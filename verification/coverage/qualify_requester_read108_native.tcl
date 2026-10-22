# Local108 fields only. Reuse proven Tcl8.4 session, selection and global reset.
set ::qfp_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/queue_fp_temporaries_native.tcl}
proc read108_walk {item stream} {
    global fma_names fma_rows fma_seen
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        qfp_select [list $path $meta $name]
        set excluded [gui_exclusion -id CovDetail.1 -excluded -selected]
        qfp_need [expr {$excluded eq "0" || $excluded eq "1"}] "Excluded flag is not Boolean"
        puts $stream [join [list $item $path $meta $name $excluded] "\t"]
        lappend fma_seen $name
        if {[lsearch -exact $fma_names $name] >= 0} {lappend fma_rows [list $path $meta $name]}
        read108_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
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
    qfp_need [expr {[llength $fma_seen] == 746 && [llength $fma_rows] == 27}] "Full746/target27 objects required"
    puts [exec $::fma_python -B $::fma_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage --index [lindex $instance 3]]
    return $fma_rows
}
proc qfp_session {} [string map [list QueueFPU0NativeOnly RequesterRead108NativeOnly \
    {Frozen FPU0 queue whole temporary, settled source constant only} \
    {Frozen nine read payloads wdata/be/wen zero after valid reset and settled evaluation; no initial-X waiver} \
    QUEUE_FP_TEMP_NATIVE_DONE REQUESTER_READ108_NATIVE_DONE] [info body qfp_session]]
if {![info exists ::read108_test_only]} {
    if {[catch {qfp_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message;puts $stream $::errorInfo;close $stream
        puts "REQUESTER_READ108_NATIVE_FAILED $message"
        catch {qfp_reset;fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
