# Exact local Toggle objects only; native paths discovered on each instance.
proc fma_need {ok why} {if {!$ok} {error $why}}
proc fma_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc fma_walk {item stream} {
    global fma_names fma_rows fma_seen
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        puts $stream "$item\t$path\t$meta\t$name"
        lappend fma_seen $name
        if {[lsearch -exact $fma_names $name] >= 0} {
            lappend fma_rows [list $path $meta $name]
        }
        fma_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc fma_bind {stage instance} {
    global fma_names fma_rows fma_seen
    set scope [lindex $instance 0]
    set fma_names [lindex $instance 1]
    set fma_rows {}
    set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle $scope
    fma_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 3].tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    fma_need [expr {[llength $fma_rows] == 9}] "Not nine unique native target rows"
    foreach name $fma_names {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        fma_need [expr {$count == 1}] "Missing/duplicate target $name"
    }
    return $fma_rows
}
proc fma_flat {selected} {
    while {[llength $selected] == 1 && [lindex $selected 0] ne $selected} {set selected [lindex $selected 0]}
    return $selected
}
proc fma_select {row} {
    set old [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -unselect $old}
    set token [lindex $row 0]
    gui_list_select -id CovDetail.1 -select [list $token]
    set selected [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    fma_need [expr {$selected eq $token || $selected eq [lindex $row 1]}] "Selection readback differs"
}
proc fma_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc fma_cleanup {} {
    fma_reset
    fma_save cleanup-empty.el
}
proc fma_check {name} {
    puts [exec $::fma_python -B $::fma_helper el --output $::env(DVE_COVERAGE_OUTPUT) --file $name]
}
proc fma_session {} {
    global env fma_instances fma_scope fma_design fma_vdb fma_test fma_python fma_helper
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge FMA108NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    foreach instance $fma_instances {fma_bind before $instance}
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) candidate.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native candidate exclusion needs review"
    foreach instance $fma_instances {fma_bind selected $instance}
    fma_save first.el
    fma_check first.el
    fma_reset
    foreach instance $fma_instances {fma_bind reset $instance}
    fma_save reset-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload needs review"
    foreach instance $fma_instances {fma_bind reloaded $instance}
    fma_save second.el
    fma_check second.el
    fma_reset
    foreach instance $fma_instances {fma_bind final $instance}
    fma_save final-empty.el
    puts FMA_DATAPATH_NATIVE_CAPTURE_DONE
}
if {[catch {fma_session} message]} {
    puts "FMA_DATAPATH_NATIVE_CAPTURE_FAILED $message"
    puts $::errorInfo
    if {[catch {fma_cleanup} cleanup]} {puts "FMA_CLEANUP_FAILED $cleanup"}
}
gui_exit -noprompt
