# Local native object selection only. No population report or final application.
proc cast_need {ok why} {if {!$ok} {error $why}}
proc cast_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc cast_select {row} {
    set old [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    foreach token $old {
        if {$token eq ""} {continue}
        gui_list_select -id CovDetail.1 -unselect [list $token]
    }
    cast_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Old selection remains"
    set token [lindex $row 0]
    gui_list_select -id CovDetail.1 -select [list $token]
    set got [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    cast_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 1 &&
                    ($got eq $token || $got eq [lindex $row 1])}] "Native selection readback differs"
}
proc cast_bind {stage instance} {
    global fma_names fma_rows fma_seen env
    set fma_names [lindex $instance 1]
    set fma_rows {}; set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    cast_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Wrong metric"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 3].tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    cast_need [expr {[llength $fma_rows] == 21}] "Missing/duplicate exact21 full numeric objects"
    foreach name [concat $fma_names [lindex $instance 2]] {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        cast_need [expr {$count == 1}] "Target/protected declaration ambiguous: $name"
    }
    puts [exec $::fma_python -B $::fma_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage --index [lindex $instance 3]]
    return $fma_rows
}
proc cast_load {} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    cast_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native reload requires review"
}
proc cast_session {} {
    global env fma_instances fma_design fma_vdb fma_test fma_python fma_helper cast_primitives
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set stream [open $cast_primitives r];set body [read $stream];close $stream
    set marker {if {[catch {fma_session} message]} }
    set pos [string first $marker $body]
    cast_need [expr {$pos > 0}] "Frozen primitive boundary differs"
    uplevel #0 [string range $body 0 [expr {$pos-1}]]
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge Cast168NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    foreach instance $fma_instances {cast_bind before $instance}
    foreach instance $fma_instances {
        foreach row [cast_bind before $instance] {
            cast_select $row
            gui_exclude_items -id CovDetail.1 -selected -annotation {Cast unchanged numeric prefix qualification only}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    cast_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native selection needs review"
    foreach instance $fma_instances {cast_bind selected $instance}
    fma_save first.el;fma_check first.el
    cast_reset
    foreach instance $fma_instances {cast_bind reset $instance}
    fma_save reset-empty.el
    cast_load
    foreach instance $fma_instances {cast_bind reloaded $instance}
    fma_save second.el;fma_check second.el
    cast_reset
    foreach instance $fma_instances {cast_bind final $instance}
    fma_save final-empty.el
    puts CAST168_NATIVE_DONE
}
if {![info exists ::cast_test_only]} {
    if {[catch {cast_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message;puts $stream $::errorInfo;close $stream
        puts "CAST168_NATIVE_FAILED $message"
        catch {cast_reset;fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
