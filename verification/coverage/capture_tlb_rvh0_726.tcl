# Tcl8.4 standalone entry; original definitions only, never their sessions.
set ::csr_test_only 1
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_csr_reserved1193.tcl
source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl
proc csv_row {stream values} {
    set escaped {}
    foreach value $values {lappend escaped "\"[string map [list \" \"\"] $value]\""}
    puts $stream [join $escaped ,]
}
proc tlb_check {stage} {
    puts [exec $::csr_python -B $::tlb_helper el --output $::env(DVE_COVERAGE_OUTPUT) --stage $stage]
}
proc tlb_capture {stage} {
    set index 0
    foreach scope $::tlb_scopes {
        p740_root
        set ::csr_scope $scope
        csr_context
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) objects-${stage}-${index}.tsv] w]
        puts $stream "path\tmeta\tname\texcluded"
        foreach row [csr_rows [gui_list_get -id CovDetail.1 -firstChild]] {
            csr_select [lindex $row 0]
            puts $stream [join [concat $row [list [gui_exclusion -id CovDetail.1 -excluded -selected]]] "\t"]
        }
        close $stream
        puts [exec $::csr_python -B $::tlb_helper inventory --output $::env(DVE_COVERAGE_OUTPUT) --stage $stage --index $index]
        incr index
    }
    p740_summary $stage
}
proc tlb_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    csr_need [expr {[llength $::tlb_scopes] == 2}] "Exact two TLB scopes"
    gui_open_cov -hier $::fma_design -testdir [list $::fma_vdb] -test [list $::fma_test] -merge TLB726LocalOnly
    foreach {stage file} {before initial-empty.el selected first.el reset reset-empty.el reloaded second.el final final-empty.el} {
        if {$stage eq "selected"} {csr_load candidate.el}
        if {$stage eq "reset" || $stage eq "final"} {csr_reset}
        if {$stage eq "reloaded"} {csr_load first.el}
        csr_save $file
        tlb_check $stage
        tlb_capture $stage
    }
    puts TLB726_NATIVE_DONE
    flush stdout
}
if {![info exists ::tlb_test_only]} {
    if {[catch {tlb_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message;puts $stream $::errorInfo;close $stream
        puts "TLB726_NATIVE_FAILED $message"
        catch {csr_reset} cleanup
        catch {csr_save cleanup-empty.el} cleanup
    }
    # Return the source script to the event loop before dispatching GUI shutdown.
    after idle {puts TLB726_EXIT_DISPATCH;flush stdout;gui_exit -noprompt}
}
