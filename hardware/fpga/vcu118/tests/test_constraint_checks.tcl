# Regression against the uploaded Vivado 2020.1 reports. Modified in-memory
# fixtures below exercise the checker, not a newly synthesized/routed design.
if {[llength [info commands try]]} { rename try {} }
source [file join [file dirname [info script]] .. scripts constraint_checks.tcl]
set dir [file normalize [lindex $argv 0]]
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
    incr ::checks
}
set checks 0
set cdc [fpga_checks::read_report [file join $dir cdc.rpt]]
set skew [fpga_checks::read_report [file join $dir bus_skew.rpt]]
assert {[llength [fpga_checks::cdc_failures $cdc]] == 61} "real report: 60 Gray and one status exception lost"
assert {[llength [fpga_checks::skew_failures $skew true]] == 10} "real report: all 10 board bus-skew groups missing"
set vendor_paths [fpga_checks::path_headers $skew]
assert {[llength $vendor_paths] == 4} "read four real vendor bus-skew path headers"
foreach path $vendor_paths {
    assert {[string match dbg_hub/* [dict get $path Destination]]} "read actual Endpoint Destination field"
}
set bad_vendor [regsub {(Slack \(MET\)\s*:)\s+19.130ns} $skew {\1 -0.001ns}]
assert {[llength [fpga_checks::skew_failures $bad_vendor true]] == 11} "vendor skew violations cannot be ignored"
assert {![llength [fpga_checks::skew_failures {} false]]} "unplaced skew path availability is not a physical signoff"
set good_cdc {}
foreach line [split $cdc \n] {
    if {[string match *i_cdc_fifo_gray*/gen_sync* $line]} {
        regsub {  None +} $line {  Max Delay Datapath Only  } line
    } elseif {[string first {gen_status_sync[2]} $line] >= 0} {
        regsub {  None +} $line {  False Path  } line
    }
    append good_cdc $line \n
}
assert {![llength [fpga_checks::cdc_failures $good_cdc]]} "complete CDC exception fixture"
assert {[llength [fpga_checks::cdc_failures {}]] == 66} "empty CDC report fails closed"
set changed [regsub {Max Delay Datapath Only} $good_cdc {False Path}]
assert {[llength [fpga_checks::cdc_failures $changed]] == 1} "broad false path cannot replace pointer bound"
set changed [regsub -line {^.*gen_sync\[5\].i_sync/reg_q_reg\[0\]/D$} $good_cdc {}]
assert {[llength [fpga_checks::cdc_failures $changed]] == 1} "every Gray bit must appear"
set changed [regsub {Max Delay Datapath Only(  [^\n]+i_spill_register/)} $good_cdc {None\1}]
assert {[llength [fpga_checks::cdc_failures $changed]] == 1} "data exceptions must remain active"

set good_skew $skew
foreach group [fpga_checks::gray_groups] {
    append good_skew "\n" [format {Slack (MET): 0.500ns
  Endpoint Source: source/C
  Endpoint Destination: %s/gen_sync[0].i_sync/reg_q_reg[0]/D
  Path Type: Bus Skew (Max at Slow Process Corner)
  Requirement: 3.000ns
} $group]
}
assert {![llength [fpga_checks::skew_failures $good_skew true]]} "10 board and 4 vendor skew groups"
set changed [regsub {Requirement: 3.000ns} $good_skew {Requirement: 20.000ns}]
assert {[llength [fpga_checks::skew_failures $changed true]] == 1} "skew bound cannot be widened"
set changed [regsub {0.500ns} $good_skew {-0.001ns}]
assert {[llength [fpga_checks::skew_failures $changed true]] == 1} "negative routed skew rejected"
assert {![llength [fpga_checks::skew_failures $changed false]]} "unrouted estimates do not block synthesis"
set changed [regsub {0.500ns} $good_skew {inf}]
assert {[llength [fpga_checks::skew_failures $changed false]] == 1} "infinite skew is never accepted"
assert {[llength [fpga_checks::skew_failures {} true]] == 10} "empty skew report fails closed"
set changed [regsub {Endpoint Destination:[^\n]+} $good_skew {}]
assert {[llength [fpga_checks::skew_failures $changed true]] == 1} "unparsed bus-skew path rejected"

# Native routed output has a constraint-level Requirement before every path.
# The next constraint's value must not overwrite the preceding path's header.
set routed_dir [file join [file dirname [info script]] .. .. ara_dsa_vcu118 reports impl_54e53e8b3aaf]
set routed_cdc [fpga_checks::read_report [file join $routed_dir cdc.rpt]]
set routed_skew [fpga_checks::read_report [file join $routed_dir bus_skew.rpt]]
assert {![llength [fpga_checks::cdc_failures $routed_cdc]]} "native routed CDC bounds restored"
assert {![llength [fpga_checks::skew_failures $routed_skew true]]} "native routed Gray and vendor skew all pass"
set routed_paths [fpga_checks::path_headers $routed_skew]
assert {[llength $routed_paths] == 14} "read 10 native Gray and 4 vendor paths"
foreach path [lrange $routed_paths 0 9] {
    assert {[dict get $path Requirement] == 3.0} "Gray path keeps its own 3 ns requirement"
}
foreach path [lrange $routed_paths 10 end] {
    assert {[dict get $path Requirement] == 20.0} "vendor path keeps its own 20 ns requirement"
}
set changed [regsub -line {^  Requirement: +3.000ns} $routed_skew {  Requirement: 20.000ns}]
assert {[llength [fpga_checks::skew_failures $changed true]] == 1} "next Gray group cannot hide a widened bound"
set changed [regsub -line {^  Requirement: +3.000ns[^\n]*} $routed_skew {}]
assert {[llength [fpga_checks::skew_failures $changed true]] == 1} "missing path requirement cannot inherit from next group"
set changed [regsub {(Slack \(MET\)\s*:)\s+2.186ns} $routed_skew {\1 -0.001ns}]
assert {[llength [fpga_checks::skew_failures $changed true]] == 1} "native Gray violation rejected"
set changed [regsub {(Slack \(MET\)\s*:)\s+18.453ns} $routed_skew {\1 -0.001ns}]
assert {[llength [fpga_checks::skew_failures $changed true]] == 1} "native vendor violation rejected"

foreach port {jtag_tck_i jtag_tms_i jtag_tdi_i uart_rx_i jtag_tdo_o uart_tx_o c0_ddr4_reset_n} {
    set report [fpga_checks::read_report [file join $dir pad_$port.rpt]]
    set missing [expr {$port in {jtag_tck_i jtag_tms_i jtag_tdi_i uart_rx_i}}]
    assert {[llength [fpga_checks::pad_exception_failures $report $port]] == $missing} \
        "real pad report $port: normal 20 ns setup must not masquerade as datapath-only"
    if {$missing} {
        append report "\n  Timing Exception: MaxDelay Path 20.000ns -datapath_only\n"
        assert {![llength [fpga_checks::pad_exception_failures $report $port]]} "explicit datapath-only fixture"
    }
}
assert {[llength [fpga_checks::pad_exception_failures {} uart_rx_i]] == 1} "missing pad report rejected"
set scratch [file normalize [lindex $argv 1]]
if {[llength $argv] != 2 || [file exists $scratch]} { error "Pass reports dir and a new scratch directory" }
file mkdir $scratch
foreach file {cdc.rpt bus_skew.rpt pad_jtag_tck_i.rpt pad_jtag_tms_i.rpt pad_jtag_tdi_i.rpt pad_uart_rx_i.rpt pad_jtag_tdo_o.rpt pad_uart_tx_o.rpt pad_c0_ddr4_reset_n.rpt} {
    file copy [file join $dir $file] [file join $scratch $file]
}
set before [lsort [chan names]]
assert {[llength [write_constraint_checks $scratch true]] == 75} "integrated checker rejects the uploaded routed snapshot"
assert {[string match {*FAILURES=75*} [fpga_checks::read_report $scratch/constraint_checks.rpt]]} "saved routed audit summary"
assert {[llength [write_constraint_checks $scratch false]] == 65} "missing CDC/pad constraints also rejected before routing"
assert {[lsort [chan names]] eq $before} "all report handles closed"
assert {[string match {*FAILURES=65*} [fpga_checks::read_report $scratch/constraint_checks.rpt]]} "saved synthesis audit summary"
puts "PASS: $checks report checks using impl_6abc9f1816a4, impl_54e53e8b3aaf and negative fixtures"
