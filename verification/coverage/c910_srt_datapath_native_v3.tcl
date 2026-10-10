# Private native calibration and candidate import; frozen helpers remain unchanged.
proc c910_primitives {} {
    set stream [open $::c910_fma_tcl r]
    set body [read $stream]
    close $stream
    set marker {if {[catch {fma_session} message]} }
    set position [string first $marker $body]
    if {$position < 0} {error "Frozen FMA entry boundary changed"}
    uplevel #0 [string range $body 0 [expr {$position - 1}]]
}
proc c910_flat {value} {
    for {set depth 0} {$depth < 16} {incr depth} {
        if {[llength $value] != 1 || [lindex $value 0] eq $value} {return $value}
        set value [lindex $value 0]
    }
    error "Excessively nested native selection"
}
proc c910_select {row} {
    set old [c910_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    foreach token $old {
        set token [c910_flat $token]
        fma_need [expr {[llength $token] == 1}] "Ambiguous old selection"
        gui_list_select -id CovDetail.1 -unselect [list $token]
    }
    fma_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Old selection remains"
    set token [lindex $row 0]
    gui_list_select -id CovDetail.1 -select [list $token]
    set selected [c910_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    fma_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 1 &&
                    ($selected eq $token || $selected eq [lindex $row 1])}] "Selection differs"
}
proc c910_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc c910_bind {stage instance} {
    global fma_names fma_rows fma_seen env
    set fma_names [lindex $instance 1]
    set fma_rows {}
    set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    fma_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 3].tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    fma_need [expr {[llength $fma_rows] == 158 && [llength $fma_seen] == 210}] "Not exact158+52 rows"
    foreach name [concat $fma_names [lindex $instance 2]] {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        fma_need [expr {$count == 1}] "Missing/duplicate target or protection $name"
    }
    puts [exec $::fma_python -B $::fma_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage --index [lindex $instance 3]]
    return $fma_rows
}
proc c910_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native import needs review"
}
proc c910_session {} {
    global env fma_instances fma_design fma_vdb fma_test fma_python fma_helper c910_fma_tcl
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    c910_primitives
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge C9101264NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    set first [lindex $fma_instances 0]
    set rows [c910_bind before $first]
    set calibration {}
    foreach row $rows {if {[lindex $row 2] eq "cur_rem\[60:0\]"} {lappend calibration $row}}
    fma_need [expr {[llength $calibration] == 1}] "No unique calibration row"
    c910_select [lindex $calibration 0]
    gui_exclude_items -id CovDetail.1 -selected -annotation {C910 declaration calibration only}
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Calibration needs review"
    fma_save calibration.el
    c910_reset
    fma_save calibration-reset-empty.el
    puts [exec $fma_python -B $fma_helper candidate --output $env(DVE_COVERAGE_OUTPUT)]
    foreach instance [lrange $fma_instances 1 end] {c910_bind before $instance}
    c910_load candidate.el
    foreach instance $fma_instances {c910_bind selected $instance}
    fma_save first.el
    fma_check first.el
    c910_reset
    foreach instance $fma_instances {c910_bind reset $instance}
    fma_save reset-empty.el
    c910_load first.el
    foreach instance $fma_instances {c910_bind reloaded $instance}
    fma_save second.el
    fma_check second.el
    c910_reset
    foreach instance $fma_instances {c910_bind final $instance}
    fma_save final-empty.el
    puts C910_SRT_NATIVE_CAPTURE_DONE
}
proc c910_failure {message detail} {
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
    puts $stream $message
    puts $stream $detail
    close $stream
    puts "C910_SRT_NATIVE_CAPTURE_FAILED $message"
    puts $detail
    if {[catch {c910_reset; fma_save cleanup-empty.el} cleanup]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] a]
        puts $stream "CLEANUP_FAILED $cleanup"
        close $stream
    }
}
if {![info exists ::c910_test_only]} {
    if {[catch {c910_session} message]} {c910_failure $message $::errorInfo}
    gui_exit -noprompt
}
