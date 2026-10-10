# Tcl8.4 full inventories; no per-object GUI select/exclusion calls.
set tied_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fpnew_tied90_local.tcl}
unset tied_test_only

proc soc_audit {stage} {
    global mq_instances qc_seen
    set index 0
    foreach instance $mq_instances {
        set scope [lindex $instance 0]
        qc_need [expr {[p740_select $scope] eq $scope}] "Exact scope token"
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        qc_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set columns {}; set labels {}
        for {set c 0} {$c < 32} {incr c} {
            if {[catch {gui_list_get_property -id CovDetail.1 -column $c} label]} {break}
            if {[string trim $label] ne ""} {lappend labels [string trim $label]; lappend columns $c}
        }
        qc_need [expr {$labels eq "Variable Type Coverage Display"}] "Unknown columns $labels"
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] w]
        puts $stream "handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay"
        set qc_seen {}
        set failed [catch {qc_walk [gui_list_get -id CovDetail.1 -firstChild] $stream $columns} message]
        close $stream
        if {$failed} {error $message}
        foreach label [lindex $instance 1] {
            set count 0
            foreach name $qc_seen {if {$name eq $label} {incr count}}
            qc_need [expr {$count == 1}] "Missing/ambiguous whole target $label"
        }
        incr index
    }
}
proc soc_gate {mode} {
    puts [exec $::tied_python -B $::tied_helper $mode --output $::env(DVE_COVERAGE_OUTPUT) --seal $::tied_seal]
}
proc soc_session {} {
    global env mq_design mq_vdb mq_test mq_instances tied_python tied_helper tied_seal
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $mq_design -testdir [list $mq_vdb] -test [list $mq_test] -merge SocConstants61LocalOnly
    p740_root
    qc_save initial-empty.el
    qc_need [expr {[file size [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]] == 0}] "Initial EL"
    soc_audit before
    soc_gate before
    mq_load candidate.el
    soc_audit applied
    qc_save first.el
    soc_gate first
    qc_reset
    soc_audit reset
    qc_save reset-empty.el
    mq_load first.el
    soc_audit reloaded
    qc_save second.el
    soc_gate second
    qc_reset
    soc_audit final
    qc_save final-empty.el
    puts SOC_CONSTANTS61_FIVE_PHASE_DONE
}
if {![info exists ::soc_test_only]} {
    if {[catch {soc_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "SOC_CONSTANTS61_FAILED $message"
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "SOC_CONSTANTS61_CLEANUP_FAILED $cleanup"}
    }
    gui_exit -noprompt
}
