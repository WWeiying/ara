# Tcl8.4-safe native bit-direction capture; every other exclusion stays protected.
proc qc_need {ok why} {if {!$ok} {error $why}}
proc qc_save {name} {gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]}
proc qc_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc qc_walk {item stream} {
    global qc_seen
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        set a [gui_list_get -id CovDetail.1 -text 1 $item]
        set b [gui_list_get -id CovDetail.1 -text 2 $item]
        puts $stream "$item\t$path\t$meta\t$name\t$a\t$b"
        lappend qc_seen $name
        qc_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc qc_audit {stage} {
    global qc_instances qc_seen
    set index 0
    foreach instance $qc_instances {
        gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
        qc_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set qc_seen {}
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] w]
        puts $f "handle\tpath\tmeta\tname\tcolumn1\tcolumn2"
        qc_walk [gui_list_get -id CovDetail.1 -firstChild] $f
        close $f
        foreach wanted [lindex $instance 1] {
            set count 0
            foreach name $qc_seen {if {$name eq $wanted} {incr count}}
            qc_need [expr {$count == 1}] "Missing/ambiguous exact source object $wanted"
        }
        incr index
    }
}
proc qc_check {name} {
    puts [exec $::qc_python -B $::qc_helper el --output $::env(DVE_COVERAGE_OUTPUT) --file $name]
}
proc qc_session {} {
    global env qc_design qc_vdb qc_test qc_instances qc_python qc_helper
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    gui_open_cov -hier $qc_design -testdir [list $qc_vdb] -test [list $qc_test] -merge QueueConstantsNativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    qc_save initial-empty.el
    qc_audit before
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) candidate.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    qc_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native bit exclusions need review"
    qc_audit selected
    qc_save first.el
    qc_check first.el
    qc_reset
    qc_audit reset
    qc_save reset-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    qc_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload needs review"
    qc_audit reloaded
    qc_save second.el
    qc_check second.el
    qc_reset
    qc_audit final
    qc_save final-empty.el
    puts QUEUE_CONSTANT_NATIVE_DONE
}
if {[catch {qc_session} message]} {
    puts "QUEUE_CONSTANT_NATIVE_FAILED $message"
    puts $::errorInfo
    if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "QUEUE_CONSTANT_CLEANUP_FAILED $cleanup"}
}
gui_exit -noprompt
