# Tcl8.4, full native complement and exact global EL in one session.
set mfb_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/mfpu_constants272_native_bind.tcl}
unset mfb_test_only
proc mq_flat {items} {
    while {[llength $items] == 1 && [lindex $items 0] ne $items} {set items [lindex $items 0]}
    return $items
}
proc mq_audit {stage flags} {
    global mq_instances qc_seen
    set index 0
    foreach instance $mq_instances {
        set scope [lindex $instance 0]
        set token [p740_select $scope]
        qc_need [expr {$token eq $scope}] "Scope token differs"
        gui_list_action -id CoverageTable.1 -column Toggle $token
        qc_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set columns {}; set labels {}
        for {set c 0} {$c < 32} {incr c} {
            if {[catch {gui_list_get_property -id CovDetail.1 -column $c} label]} {break}
            if {[string trim $label] ne ""} {lappend labels [string trim $label]; lappend columns $c}
        }
        qc_need [expr {$labels eq "Variable Type Coverage Display"}] "Unknown columns $labels"
        set path [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv]
        set stream [open $path w]
        puts $stream "handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay"
        set qc_seen {}
        set failed [catch {qc_walk [gui_list_get -id CovDetail.1 -firstChild] $stream $columns} message]
        close $stream
        if {$failed} {error $message}
        foreach label [lindex $instance 1] {
            set count 0
            foreach name $qc_seen {if {$name eq $label} {incr count}}
            qc_need [expr {$count == 1}] "Missing/ambiguous target $label"
            set selected [mq_flat [gui_list_get_selected -id CovDetail.1 -flat]]
            if {[llength $selected]} {gui_list_select -id CovDetail.1 -unselect $selected}
            gui_list_select -id CovDetail.1 -select [list $label]
            set selected [mq_flat [gui_list_get_selected -id CovDetail.1 -flat]]
            qc_need [expr {$selected eq $label}] "Target readback differs"
            set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
            qc_need [expr {$flag eq "0" || $flag eq "1"}] "Unknown excluded flag"
            puts $flags [join [list $stage $scope $label $flag] "\t"]
        }
        flush $flags
        incr index
    }
}
proc mq_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    qc_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Needs review"
}
proc mq_session {} {
    global env mq_design mq_vdb mq_test mq_instances
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $mq_design -testdir [list $mq_vdb] -test [list $mq_test] -merge MFPU272LocalOnly
    p740_root
    qc_save initial-empty.el
    qc_need [expr {[file size [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]] == 0}] "Initial EL not empty"
    set flags [open [file join $env(DVE_COVERAGE_OUTPUT) flags.tsv] w]
    puts $flags "stage\tscope\tlabel\texcluded"
    mq_audit before $flags
    mq_load candidate.el
    mq_audit applied $flags
    qc_save first.el
    qc_reset
    mq_audit reset $flags
    qc_save reset-empty.el
    mq_load first.el
    mq_audit reloaded $flags
    qc_save second.el
    qc_reset
    mq_audit final $flags
    qc_save final-empty.el
    close $flags
    puts MFPU272_FIVE_PHASE_DONE
}
if {![info exists ::mq_test_only]} {
    if {[catch {mq_session} message]} {
        puts "MFPU272_FIVE_PHASE_FAILED $message"
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "MFPU272_CLEANUP_FAILED $cleanup"}
    }
    gui_exit -noprompt
}
