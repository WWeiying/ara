# Local whole typed fields only, Tcl8.4 compatible, bracket names are data.
proc qfp_need {ok why} {if {!$ok} {error $why}}
proc qfp_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc qfp_select {row} {
    foreach token [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]] {
        if {$token ne ""} {gui_list_select -id CovDetail.1 -unselect [list $token]}
    }
    qfp_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Old selection remains"
    set token [lindex $row 0]
    gui_list_select -id CovDetail.1 -select [list $token]
    set got [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    qfp_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 1 &&
                    ($got eq $token || $got eq [lindex $row 1])}] "Exact native selected identity differs"
}
proc qfp_bind {stage instance} {
    global fma_names fma_rows fma_seen env
    set fma_names [lindex $instance 1]; set fma_rows {}; set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    qfp_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 3].tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    qfp_need [expr {[llength $fma_rows] == 21}] "Not exact21 whole fields"
    foreach name [concat $fma_names [lindex $instance 2]] {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        qfp_need [expr {$count == 1}] "Missing/ambiguous target/protection: $name"
    }
    puts [exec $::fma_python -B $::fma_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage --index [lindex $instance 3]]
    return $fma_rows
}
proc qfp_session {} {
    global env fma_design fma_vdb fma_test fma_python fma_helper fma_instances qfp_primitives
    source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set stream [open $::qfp_primitives r]; set body [read $stream]; close $stream
    set pos [string first {if {[catch {fma_session} message]} } $body]
    qfp_need [expr {$pos > 0}] "Frozen primitive boundary differs"
    uplevel #0 [string range $body 0 [expr {$pos-1}]]
    gui_open_cov -hier $::fma_design -testdir [list $::fma_vdb] -test [list $::fma_test] -merge QueueFPU0NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el; fma_check initial-empty.el
    foreach instance $::fma_instances {qfp_bind before $instance}
    foreach instance $::fma_instances {
        foreach row [qfp_bind before $instance] {
            qfp_select $row
            gui_exclude_items -id CovDetail.1 -selected -annotation {Frozen FPU0 queue whole temporary, settled source constant only}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    qfp_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Selected exclusion needs review"
    foreach instance $::fma_instances {qfp_bind selected $instance}
    fma_save first.el; fma_check first.el
    qfp_reset
    foreach instance $::fma_instances {qfp_bind reset $instance}
    fma_save reset-empty.el; fma_check reset-empty.el
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    qfp_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload needs review"
    foreach instance $::fma_instances {qfp_bind reloaded $instance}
    fma_save second.el; fma_check second.el
    qfp_reset
    foreach instance $::fma_instances {qfp_bind final $instance}
    fma_save final-empty.el; fma_check final-empty.el
    puts QUEUE_FP_TEMP_NATIVE_DONE
}
if {![info exists ::qfp_test_only]} {
    if {[catch {qfp_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message; puts $stream $::errorInfo; close $stream
        puts "QUEUE_FP_TEMP_NATIVE_FAILED $message"
        catch {qfp_reset; fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
