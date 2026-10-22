# Local-only five-phase driver. Parent launches only after independent review.
set soc_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/soc_constants61_native.tcl}
unset soc_test_only
set csr_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_csr_reserved1193.tcl}
unset csr_test_only

proc c1424_gate {args} {
    puts [eval exec [list $::tied_python -B $::tied_helper] $args \
        [list --output $::env(DVE_COVERAGE_OUTPUT) --seal $::tied_seal]]
}
proc c1424_capture {stage} {
    soc_audit $stage
    set index 0
    foreach instance $::mq_instances {
        set scope [lindex $instance 0]
        qc_need [expr {[p740_select $scope] eq $scope}] "Exact child scope"
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        qc_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Native Toggle context"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set rows [csr_rows [gui_list_get -id CovDetail.1 -firstChild]]
        set paths {}
        foreach label [lindex $instance 1] {
            set matches {}
            foreach row $rows {if {[lindex $row 2] eq $label} {lappend matches [lindex $row 0]}}
            qc_need [expr {[llength $matches] == 1}] "Unique actual full-vector path"
            set path [lindex $matches 0]
            lappend paths $path
            csr_select $path
            gui_cov_tgl_double_click -id CovDetail.1 -item $path
        }
        gui_process_events -mstime 100
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) bits_${stage}_${index}.tsv] w]
        puts $stream "signal\tbit\tpath\tmeta\tname\tcoverage\t0to1\t1to0"
        foreach row [csr_rows [gui_list_get -id CovDetail.1 -firstChild]] {
            set name [lindex $row 2]
            if {[regexp {^(initial_divisor_in|initial_remainder_in)\[([0-9]+)\]$} $name ignored signal bit]} {
                set path [lindex $row 0]
                csr_select $path
                set coverage [string trim [gui_list_get -id CovDetail.1 -text 2 $path]]
                set rise [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 0to1]
                set fall [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 1to0]
                puts $stream [join [concat [list $signal $bit] $row [list $coverage $rise $fall]] "\t"]
            }
        }
        close $stream
        # Restore compressed inventory; partial-bit identity comes only from actual labels.
        foreach path $paths {gui_cov_tgl_double_click -id CovDetail.1 -item $path}
        gui_process_events -mstime 100
        incr index
    }
    c1424_gate inventory --stage $stage
}
proc c1424_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    qc_need [expr {[llength $::mq_instances] == 8}] "Eight exact instances"
    c1424_gate check
    help gui_cov_tgl_double_click
    help gui_exclusion
    set dirs [glob -types d -directory [file join $::mq_vdb snps coverage db testdata] *]
    qc_need [expr {[llength $dirs] == 1}] "One admitted sample"
    set actual [file join [file rootname $::mq_vdb] [file tail [lindex $dirs 0]]]
    qc_need [expr {$actual eq $::mq_test}] "Actual sample identity"
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $f $actual; close $f
    gui_open_cov -hier $::mq_design -testdir [list $::mq_vdb] -test [list $actual] -merge C9101424LocalOnly
    p740_root
    qc_save initial-empty.el
    qc_need [expr {[file size [file join $::env(DVE_COVERAGE_OUTPUT) initial-empty.el]] == 0}] "Global initial empty"
    c1424_capture before
    mq_load candidate.el
    c1424_capture applied
    qc_save first.el
    c1424_gate el --file first.el
    qc_reset
    c1424_capture reset
    qc_save reset-empty.el
    mq_load first.el
    c1424_capture reloaded
    qc_save second.el
    c1424_gate el --file second.el
    qc_reset
    c1424_capture final
    qc_save final-empty.el
}
if {![info exists ::c1424_test_only]} {
    if {[catch {c1424_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "C9101424_FAILED $message"
        catch {qc_reset} cleanup
        catch {qc_save cleanup-empty.el} cleanup
    } else {puts C9101424_FIVE_PHASE_DONE}
    gui_exit -noprompt
}
