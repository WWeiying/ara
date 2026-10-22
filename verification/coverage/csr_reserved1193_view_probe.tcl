# Read-only two-object diagnosis. Never imports/excludes/saves an exclusion file.
set ::csr_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_csr_reserved1193.tcl}

proc csr_probe_rows {label} {
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) expanded-${label}.tsv] w]
    puts $f "path\tmeta\tname"
    foreach row [csr_rows [gui_list_get -id CovDetail.1 -firstChild]] {
        puts $f [join $row "\t"]
    }
    close $f
    # Dump the default list's real widget contract too; do not assume this is the bit pane.
    gui_dump_common_list -id CovDetail.1
}
proc csr_probe {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    help gui_cov_tgl_compress
    help gui_cov_tgl_can_compress
    help gui_dump_common_list
    gui_open_cov -hier $::fma_design -testdir [list $::fma_vdb] -test [list $::fma_test] -merge CSR1193ReadOnlyProbe
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set index 0
    foreach name [list {dcache_q[63:0]} {mstatus_q.uxl[1:0]}] {
        csr_context
        csr_probe_rows before-${index}
        csr_select $name
        set allowed [gui_cov_tgl_can_compress -id CovDetail.1 -opt uncompress]
        puts "CSR1193_UNCOMPRESS_AVAILABLE $index $name $allowed"
        csr_need [expr {$allowed eq "1"}] "Documented uncompress unavailable"
        gui_cov_tgl_compress -id CovDetail.1 -opt uncompress
        gui_process_events -mstime 100
        csr_probe_rows after-${index}
        incr index
    }
    puts CSR1193_READONLY_PROBE_DONE_NOT_QUALIFICATION
}
if {![info exists ::csr_probe_test_only]} {
    if {[catch {csr_probe} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) probe-error.txt] w]
        puts $f $message; puts $f $::errorInfo;close $f
        puts "CSR1193_READONLY_PROBE_FAILED $message"
    }
    gui_exit -noprompt
}
