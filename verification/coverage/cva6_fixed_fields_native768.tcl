# Tcl8.4: exact candidate load, five native inventories, global EL roundtrip.
proc qc_need {ok why} {if {!$ok} {error $why}}
proc qc_save {name} {gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]}
proc qc_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc qc_walk {item stream columns} {
    global qc_seen
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set values {}
        foreach column $columns {
            set value [string trim [gui_list_get -id CovDetail.1 -text $column $item]]
            qc_need [expr {[string first "\t" $value] < 0 && [string first "\n" $value] < 0}] "Multiline native cell"
            lappend values $value
        }
        lappend qc_seen [lindex $values 0]
        puts $stream [join [concat [list $item $path $meta] $values] "\t"]
        qc_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream $columns
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
        set columns {}; set labels {}
        for {set c 0} {$c < 32} {incr c} {
            if {[catch {gui_list_get_property -id CovDetail.1 -column $c} label]} {break}
            if {[string trim $label] ne ""} {lappend labels [string trim $label]; lappend columns $c}
        }
        qc_need [expr {$labels eq "Variable Type Coverage Display"}] "Unknown native columns $labels"
        set qc_seen {}
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] w]
        puts $f "handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay"
        qc_walk [gui_list_get -id CovDetail.1 -firstChild] $f $columns
        close $f
        foreach wanted [lindex $instance 1] {
            set count 0
            foreach name $qc_seen {if {$name eq $wanted} {incr count}}
            qc_need [expr {$count == 1}] "Missing/ambiguous source object $wanted"
        }
        incr index
    }
}
proc qc_check {name} {
    puts [exec $::qc_python -B $::qc_helper el --output $::env(DVE_COVERAGE_OUTPUT) --file $name]
}
proc qc_session {} {
    global env qc_design qc_vdb qc_test qc_instances qc_python qc_helper
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $qc_design -testdir [list $qc_vdb] -test [list $qc_test] -merge CVA6Fixed120Only
    gui_list_expand -id CoverageTable.1 -all {<root>}
    qc_save initial-empty.el
    qc_audit before
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) candidate.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    qc_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Apply needs review"
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
if {![info exists ::qc_test_only]} {
    if {[catch {qc_session} message]} {
        puts "QUEUE_CONSTANT_NATIVE_FAILED $message"
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        if {[catch {qc_reset; qc_save cleanup-empty.el} cleanup]} {puts "QUEUE_CONSTANT_CLEANUP_FAILED $cleanup"}
    }
    gui_exit -noprompt
}
