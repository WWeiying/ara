# Fixed absolute source paths; all native-entry syntax is Tcl8.4-compatible.
set ::c910_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/c910_srt_datapath_native_v3.tcl}
proc pp_check {mode args} {
    set command [list exec $::pp_python -B $::pp_helper $mode --output $::env(DVE_COVERAGE_OUTPUT) --seal $::env(C910_PREPARE_PACK_SEAL)]
    puts [eval [concat $command $args]]
}
proc pp_bind {stage instance} {
    global fma_names fma_rows fma_seen
    set fma_names [lindex $instance 1]
    set fma_rows {}
    set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    fma_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 3].tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    fma_need [expr {[llength $fma_rows] == [llength $fma_names] &&
                    [llength $fma_seen] == [llength [lindex $instance 2]]}] "Target/full guard count differs"
    foreach name [lindex $instance 2] {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        fma_need [expr {$count == 1}] "Missing/duplicate exact native name $name"
    }
    return $fma_rows
}
proc pp_stage {stage} {
    foreach instance $::pp_instances {pp_bind $stage $instance}
    pp_check stage --stage $stage
    puts "C910_PREPARE_PACK_STAGE_OK $stage"
}
proc pp_session {} {
    source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]
    foreach variable {pp_instances pp_design pp_vdb pp_test pp_python pp_helper c910_fma_tcl} {
        if {![info exists ::$variable]} {error "Unbound selection variable $variable"}
    }
    set ::fma_python $::pp_python
    set ::fma_helper $::pp_helper
    c910_primitives
    gui_open_cov -hier $::pp_design -testdir [list $::pp_vdb] -test [list $::pp_test] -merge C910PreparePack240NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    pp_stage initial
    foreach index {0 16} {
        foreach row [pp_bind calibration [lindex $::pp_instances $index]] {
            set is_pack [lsearch -exact {ex4_frac[54:0] ex4_frac_52[51:0]} [lindex $row 2]]
            if {($index == 0 && $is_pack >= 0) ||
                ($index == 16 && [lindex $row 2] eq {ex1_oper0_frac[51:0]})} {
                c910_select $row
                gui_exclude_items -id CovDetail.1 -selected -annotation {Exact arithmetic source type calibration}
            }
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Calibration review unresolved"
    fma_save calibration.el
    c910_reset
    fma_save calibration-reset-empty.el
    pp_check calibration
    c910_load candidate.el
    fma_save first.el
    pp_stage apply
    c910_reset
    fma_save reset-empty.el
    pp_stage reset
    c910_load first.el
    fma_save second.el
    pp_stage reload
    c910_reset
    fma_save final-empty.el
    pp_stage final
    puts C910_PREPARE_PACK_NATIVE_DONE
}
if {![info exists ::pp_test_only]} {
    if {[catch {pp_session} message]} {
        puts "C910_PREPARE_PACK_NATIVE_FAILED $message"
        c910_failure $message $::errorInfo
    }
    gui_exit -noprompt
}
