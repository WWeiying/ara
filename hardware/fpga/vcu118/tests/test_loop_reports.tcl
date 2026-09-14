# Offline checks for diagnostic extraction and the pre-implementation gate.
# Reproduce the missing command in the Windows Vivado 2020.1 interpreter.
if {[llength [info commands try]]} { rename try {} }
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
proc get_cells {args} {
    if {[lsearch -exact $args -hierarchical] >= 0} {
        assert {[lindex $args end] eq "NAME =~ */i_fpga_compute_fault"} "fixed fault LUT lookup"
        return [expr {$::has_fault_guard ? "qbs/i_fpga_compute_fault" : ""}]
    }
    set objects [lindex $args end]
    if {$objects eq "LUTLP-1#1"} { return {qbs/needed_LUT qbs/read_LUT} }
    set result {}
    foreach pin $objects { lappend result [file dirname $pin] }
    return $result
}
proc list_property {cell} { return {REF_NAME INIT DONT_TOUCH ORIG_CELL_NAME} }
proc get_property {key object} {
    switch $key {
        REF_NAME { return [expr {$object eq "qbs/state_reg" ? "FDRE" : "LUT2"}] }
        IS_SEQUENTIAL { return [expr {$object eq "qbs/state_reg"}] }
        INIT { return 4'h8 }
        DONT_TOUCH { return TRUE }
        ORIG_CELL_NAME { return $object }
        DIRECTION { return [expr {[string match */O $object] ? "OUT" : "IN"}] }
        default { error "Unexpected property $key" }
    }
}
proc get_pins {args} {
    if {[lsearch -exact $args -leaf] >= 0} {
        set net [lindex $args [expr {[lsearch -exact $args -of_objects]+1}]]
        set pin [file dirname $net]
        switch $pin {
            qbs/needed_LUT/I0 { return qbs/read_LUT/O }
            qbs/needed_LUT/I1 { return qbs/support_LUT/O }
            qbs/read_LUT/I0 { return qbs/needed_LUT/O }
            qbs/read_LUT/I1 - qbs/support_LUT/I0 { return qbs/state_reg/Q }
            qbs/i_fpga_compute_fault/I0 - qbs/i_fpga_compute_fault/I1 { return qbs/state_reg/Q }
            qbs/support_LUT/I1 { return {} }
            default { return $pin }
        }
    }
    set cell [lindex $args end]
    assert {$cell ne "qbs/state_reg"} "do not follow sequential cells to their inputs"
    return [list $cell/I0 $cell/I1 $cell/O]
}
proc get_nets {args} {
    assert {[lsearch -exact $args -segments] >= 0} "include net segments across hierarchy"
    return [lindex $args end]/net
}
proc get_ports {args} {
    return [expr {[lindex $args end] eq "qbs/support_LUT/I1/net" ? "reset_i" : ""}]
}
set has_loop 1
assert {[write_loop_details $dir] == 1} "return violation count"
set f [open $dir/loop_cells.rpt r]; set report [read $f]; close $f
foreach text {"CELL qbs/needed_LUT REF_NAME=LUT2" "INIT=4'h8" "DRIVERS=qbs/read_LUT/O"} {
    assert {[string first $text $report] >= 0} "diagnostic missing $text"
}
set f [open $dir/loop_fanin.rpt r]; set fanin [read $f]; close $f
foreach text {"CELL qbs/support_LUT" "CELL qbs/state_reg REF_NAME=FDRE" "BOUNDARY sequential" "PORTS=reset_i" "Visited 4 cells; pending 0"} {
    assert {[string first $text $fanin] >= 0} "fanin diagnostic missing $text"
}
write_loop_fanin $dir qbs/needed_LUT 1
set f [open $dir/loop_fanin.rpt r]; set fanin [read $f]; close $f
assert {[string first "TRUNCATED:" $fanin] >= 0} "node limit must be explicit"
assert {[catch {require_no_combinational_loops $dir} message]} "loops block implementation"
assert {[string match "Combinational loops remain*" $message]} "actionable error"
set has_loop 0
assert {[write_loop_details $dir] == 0} "clean design count"
set f [open $dir/loop_fanin.rpt r]; set fanin [read $f]; close $f
assert {[string first "Visited 0 cells; pending 0" $fanin] >= 0} "clean design has empty fanin"
assert {[catch {write_loop_fanin $dir {} 0}]} "invalid node bound must fail"
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
set has_fault_guard 1
write_reports clean true
set f [open $dir/reports/clean/fault_decode.rpt r]; set fault [read $f]; close $f
foreach text {"CELL qbs/i_fpga_compute_fault" "DONT_TOUCH=TRUE" "BOUNDARY sequential" "Visited 2 cells; pending 0"} {
    assert {[string first $text $fault] >= 0} "fixed fault diagnostic missing $text"
}
set has_fault_guard 0
set has_loop 1
write_reports inspect
set f [open $dir/reports/inspect/fault_decode.rpt r]; set fault [read $f]; close $f
assert {[string first "Visited 0 cells; pending 0" $fault] >= 0} "old netlist has no fixed fault LUT"
set f [open $dir/reports/inspect/loop_fanin.rpt r]; set fanin [read $f]; close $f
assert {[string first "CELL qbs/needed_LUT" $fanin] >= 0} "fault report does not overwrite loop report"
assert {[catch {write_reports route true} message]} "post-route loops must fail"
assert {[string match "Combinational loops remain*" $message]} "post-route loop diagnosis"

rename write_cell_details real_write_cell_details
proc write_cell_details {out cell} {
    if {$::detail_failure} {
        return -code error -errorcode {ARA TEST DETAIL} "Cannot read cell"
    }
    return [real_write_cell_details $out $cell]
}
rename close real_close
proc close {channel} {
    real_close $channel
    if {$::close_failure} {
        return -code error -errorcode {ARA TEST CLOSE} "Cannot flush report"
    }
}
foreach entry {write_loop_details write_loop_fanin} {
    foreach failure {detail close both} {
        set detail_failure [expr {$failure in {detail both}}]
        set close_failure [expr {$failure in {close both}}]
        set before [lsort [chan names]]
        set command [list $entry $dir]
        if {$entry eq "write_loop_fanin"} { lappend command qbs/needed_LUT }
        set code [catch {{*}$command} message options]
        assert {$code == 1} "$entry: propagate report failures"
        set expected [expr {$detail_failure ? "ARA TEST DETAIL" : "ARA TEST CLOSE"}]
        set expected_message [expr {$detail_failure ? "Cannot read cell" : "Cannot flush report"}]
        assert {[dict get $options -errorcode] eq $expected} "$entry: preserve failure code"
        assert {$message eq $expected_message} "$entry: preserve failure message"
        assert {[string first $entry [dict get $options -errorinfo]] >= 0} "$entry: preserve stack"
        assert {[lsort [chan names]] eq $before} "$entry: report channel must be closed"
        puts "PASS $entry $failure cleanup"
    }
}
rename close {}
rename real_close close
puts "PASS: loop cell connectivity, INIT, inspection and pre/post-implementation gates"
