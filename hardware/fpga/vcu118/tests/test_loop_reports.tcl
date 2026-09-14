# Offline checks for diagnostic extraction and the pre-implementation gate.
source [file join [file dirname [info script]] .. scripts common.tcl]
set dir [file normalize [lindex $argv 0]]
file mkdir $dir
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc report_drc {args} {
    assert {[lrange $args 0 3] eq "-checks LUTLP-1 -name ara_loops"} "run the actual loop DRC"
}
proc get_drc_violations {args} { return [expr {$::has_loop ? "LUTLP-1#1" : ""}] }
proc get_cells {args} { return {qbs/needed_LUT qbs/read_LUT} }
proc list_property {cell} { return {REF_NAME INIT ORIG_CELL_NAME} }
proc get_property {key object} {
    switch $key {
        REF_NAME { return LUT2 }
        INIT { return 4'h8 }
        ORIG_CELL_NAME { return $object }
        DIRECTION { return [expr {[string match */O $object] ? "OUT" : "IN"}] }
        default { error "Unexpected property $key" }
    }
}
proc get_pins {args} {
    if {[lsearch -exact $args -leaf] >= 0} { return qbs/driver/O }
    set cell [lindex $args end]
    return [list $cell/I0 $cell/I1 $cell/O]
}
proc get_nets {args} {
    assert {[lsearch -exact $args -segments] >= 0} "include net segments across hierarchy"
    return qbs/feedback
}
proc get_ports {args} { return {} }
set has_loop 1
assert {[write_loop_details $dir] == 1} "return violation count"
set f [open $dir/loop_cells.rpt r]; set report [read $f]; close $f
foreach text {"CELL qbs/needed_LUT REF_NAME=LUT2" "INIT=4'h8" "DRIVERS=qbs/driver/O"} {
    assert {[string first $text $report] >= 0} "diagnostic missing $text"
}
assert {[catch {require_no_combinational_loops $dir} message]} "loops block implementation"
assert {[string match "Combinational loops remain*" $message]} "actionable error"
set has_loop 0
assert {[write_loop_details $dir] == 0} "clean design count"
require_no_combinational_loops $dir
foreach cmd {report_utilization report_timing_summary check_timing report_cdc
    report_clock_interaction report_timing report_exceptions report_clocks} {
    proc $cmd {args} {}
}
rename report_drc loop_report_drc
proc report_drc {args} {
    if {[lsearch -exact $args -checks] >= 0} { loop_report_drc {*}$args }
}
set package_root $dir
write_reports clean true
set has_loop 1
write_reports inspect
assert {[catch {write_reports route true} message]} "post-route loops must fail"
assert {[string match "Combinational loops remain*" $message]} "post-route loop diagnosis"
puts "PASS: loop cell connectivity, INIT, inspection and pre/post-implementation gates"
