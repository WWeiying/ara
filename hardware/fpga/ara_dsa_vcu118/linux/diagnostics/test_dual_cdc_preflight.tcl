set ::dual_cdc_preflight_library_only true
source [file join [file dirname [info script]] dual_cdc_preflight.tcl]
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Expected a new test directory"}
file mkdir $root
namespace eval ara_cdc {}
proc get_pins {args} {
    if {[lsearch -exact $args -of_objects]>=0} {return [lindex $args 2]}
    set p [lindex $args end]
    if {$::scenario eq "missing_channel" && $p eq "gen_ddr2.i_dram_wrapper_c2/soc_clk_i"} {return {}}
    return $p
}
proc get_clocks {args} {
    set p [lindex $args end]
    if {$p eq "dbg_hub/clk"} {return [expr {$::scenario eq "wrong_debug" ? "ui75" : "soc"}]}
    return soc
}
proc get_property {key object} {return 20.0}
proc get_cells {args} {
    if {[string match *gen_sync* [lindex $args end]]} {
        return {r0 r1 r2 r3 r4 r5 r6 r7 r8 r9 r10 r11}
    }
    if {$::scenario eq "missing_data"} {return {}}
    return {d0 d1}
}
proc filter {args} {
    if {$::scenario eq "missing_gray"} {return {r0 r1 r2 r3 r4}}
    return {r0 r1 r2 r3 r4 r5}
}
proc report_timing {args} {
    incr ::reports
    set file [lindex $args end]
    if {$::scenario eq "lost_exception" && [file tail $file] eq "c2_r_data.rpt"} {
        return {Requirement: 3.333ns}
    }
    if {$::scenario eq "relaxed_bound"} {return "Timing Exception: MaxDelay Path 5.000ns -datapath_only\nRequirement: 5.000ns"}
    if {$::scenario eq "wrong_exception"} {return "Timing Exception: MaxDelay Path 3.000ns\nRequirement: 3.000ns"}
    return "Timing Exception: MaxDelay Path 3.000ns -datapath_only\nRequirement: 3.000ns"
}
foreach scenario {healthy marker_absent marker_false wrong_debug missing_channel missing_data missing_gray lost_exception relaxed_bound wrong_exception reopened_checkpoint} {
    set ::reports 0
    set ::ara_cdc::application_complete [expr {$scenario ne "marker_false"}]
    if {$scenario eq "marker_absent"} {unset ::ara_cdc::application_complete}
    set output [file join $root $scenario]
    set failed [catch {dual_cdc_preflight $output [expr {$scenario ne "reopened_checkpoint"}]} message]
    set expected [expr {$scenario ni {healthy reopened_checkpoint}}]
    if {$failed != $expected} {error "Unexpected $scenario: $message"}
    if {!$failed && $::reports!=30} {error "Incomplete effective exception inventory"}
    if {$failed && [file exists [file join $output completed.txt]]} {error "False success marker"}
    puts "PASS $scenario"
}
