# Reuse the proven inventory and root-selection primitives, not their sessions.
set ::mq_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/mfpu272_five_phase.tcl}
unset ::mq_test_only
proc cp_gate {stage} {
    puts [exec $::cp_python -B $::cp_helper stage --output $::env(DVE_COVERAGE_OUTPUT) --seal $::cp_seal --stage $stage]
}
proc cp_audit {stage flags} {
    # mq_audit binds every typed row; its target flag is aggregate, not bit authority.
    mq_audit $stage $flags
    set index 0
    foreach instance $::mq_instances {
        set token [p740_select [lindex $instance 0]]
        qc_need [expr {$token eq [lindex $instance 0]}] "Exact scope selection"
        gui_list_action -id CoverageTable.1 -column Toggle $token
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) excluded_${stage}_${index}.tsv] w]
        puts $stream "label\texcluded"
        set input [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] r]
        gets $input header
        while {[gets $input line] >= 0} {
            set label [lindex [split $line "\t"] 3]
            set selected [mq_flat [gui_list_get_selected -id CovDetail.1 -flat]]
            if {[llength $selected]} {gui_list_select -id CovDetail.1 -unselect $selected}
            gui_list_select -id CovDetail.1 -select [list $label]
            qc_need [expr {[mq_flat [gui_list_get_selected -id CovDetail.1 -flat]] eq $label}] "Exact complement selection"
            set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
            qc_need [expr {$flag eq "0" || $flag eq "1"}] "Native aggregate flag encoding"
            puts $stream [join [list $label $flag] "\t"]
        }
        close $input;close $stream;incr index
    }
}
proc cp_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $::mq_design -testdir [list $::mq_vdb] -test [list $::mq_test] -merge ClassPaddingLocalOnly
    p740_root
    qc_save inherited-before-clear.el
    qc_reset
    set flags [open [file join $::env(DVE_COVERAGE_OUTPUT) aggregate-target-flags.tsv] w]
    puts $flags "stage\tscope\tlabel\texcluded"
    foreach stage {before applied reset reloaded final} file {initial-empty.el first.el reset-empty.el second.el final-empty.el} {
        if {$stage eq "applied"} {mq_load candidate.el}
        if {$stage eq "reloaded"} {mq_load first.el}
        if {$stage eq "reset" || $stage eq "final"} {qc_reset}
        qc_save $file
        cp_audit $stage $flags
        cp_gate $stage
    }
    close $flags
    qc_reset;qc_save cleanup-empty.el
    puts FPNEW_CLASS_PADDING_NATIVE_DONE
}
if {![info exists ::cp_test_only]} {
    if {[catch {cp_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message;puts $stream $::errorInfo;close $stream
        puts "FPNEW_CLASS_PADDING_FAILED $message"
        catch {qc_reset} cleanup
        catch {qc_save cleanup-empty.el} cleanup
    }
    gui_exit -noprompt
}
