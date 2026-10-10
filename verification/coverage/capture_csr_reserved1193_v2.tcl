# Exact native partial-bit membership authority; no claim of per-bit GUI readback.
set ::csr_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_csr_reserved1193.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}

proc csv_row {stream fields} {
    set quoted {}
    foreach field $fields {lappend quoted "\"[string map [list \" \"\"] $field]\""}
    puts $stream [join $quoted ,]
}
proc csr2_capture {stage} {
    p740_root
    csr_context
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) objects-${stage}.tsv] w]
    puts $stream "path\tmeta\tname\texcluded"
    foreach row [csr_rows [gui_list_get -id CovDetail.1 -firstChild]] {
        csr_select [lindex $row 0]
        set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
        puts $stream [join [concat $row [list $flag]] "\t"]
    }
    close $stream
    puts [exec $::csr_python -B $::csr2_helper inventory --output $::env(DVE_COVERAGE_OUTPUT) --stage $stage]
    # Proven rooted contract: cumulative, show ratio, fresh root and event processing.
    p740_summary $stage
}
proc csr2_check {stage} {
    puts [exec $::csr_python -B $::csr2_helper el --output $::env(DVE_COVERAGE_OUTPUT) --stage $stage]
}
proc csr2_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $::fma_design -testdir [list $::fma_vdb] -test [list $::fma_test] -merge CSR1193V2LocalOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    csr_save initial-empty.el;csr2_check before;csr2_capture before
    csr_load candidate.el
    csr_save first.el;csr2_check selected;csr2_capture selected
    csr_reset
    csr_save reset-empty.el;csr2_check reset;csr2_capture reset
    csr_load first.el
    csr_save second.el;csr2_check reloaded;csr2_capture reloaded
    csr_reset
    csr_save final-empty.el;csr2_check final;csr2_capture final
    puts CSR1193_V2_NATIVE_DONE
}
if {![info exists ::csr2_test_only]} {
    if {[catch {csr2_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message;puts $stream $::errorInfo;close $stream
        puts "CSR1193_V2_NATIVE_FAILED $message"
        catch {csr_reset} cleanup
        catch {csr_save cleanup-empty.el} cleanup
    }
    gui_exit -noprompt
}
