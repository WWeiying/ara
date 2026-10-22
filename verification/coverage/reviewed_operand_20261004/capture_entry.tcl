# One compiled VDB plus one independently admitted PASS. No hierarchy export.
proc operand_capture_entry {} {
    global env
    set f [open [file join $env(DVE_COVERAGE_OUTPUT) inputs.txt] r]
    set inputs [split [string trim [read $f]] "\n"]
    close $f
    if {[llength $inputs] != 2} {error "Capture requires exactly two input VDBs"}
    set design [lindex $inputs 0]
    set db [lindex $inputs 1]
    set dirs [glob -types d -directory [file join $db snps coverage db testdata] *]
    if {[llength $dirs] != 1} {error "Capture requires one PASS test"}
    set test [file join [file rootname $db] [file tail [lindex $dirs 0]]]
    set f [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $f $test
    close $f
    gui_open_cov -hier $design -testdir [list $db] -test [list $test] -merge OperandIdentityOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    source [file join $env(OPERAND_BUNDLE) dve_operand.tcl]
    apply_reviewed_waivers CoverageTable.1
    puts DVE_COVERAGE_EXPORT_DONE
}
if {[catch {operand_capture_entry} message]} {puts "OPERAND_CAPTURE_FAILED $message\n$::errorInfo"}
gui_exit -noprompt
