# Query fixtures, not native Vivado/URAM validation.
source [file join [file dirname [info script]] .. scripts warning_details.tcl]
if {[llength $argv] != 1 || [file exists [lindex $argv 0]]} { error "Pass a new test directory" }
set sandbox [file normalize [lindex $argv 0]]
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc option {args name} { return [lindex $args [expr {[lsearch -exact $args $name] + 1}]] }
proc get_cells {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {
        if {$::scenario eq "missing_driver"} { return {} }
        return [file dirname [option $args -of_objects]]
    }
    set filter [option $args -filter]
    if {$filter eq {REF_NAME == URAM288}} {
        return [expr {$::scenario eq "missing_uram" ? {} : "uram"}]
    }
    if {![regexp {^NAME == "([^"]+)"$} $filter -> name]} { error "Unexpected cell query: $filter" }
    if {$::scenario eq "missing_status" && [string match gen_status* $name]} { return {} }
    return [list $name]
}
proc get_property {key object} {
    set object [lindex $object 0]
    switch $key {
        NAME { return $object }
        REF_NAME { return [expr {$object eq "logic" ? "LUT1" : $object}] }
        ASYNC_REG { return TRUE }
        CASCADE_ORDER_A - CASCADE_ORDER_B {
            if {$::scenario eq "unknown_order"} { return {} }
            if {$::scenario in {FIRST MIDDLE LAST}} { return $::scenario }
            return NONE
        }
        default { error "Unexpected property: $key" }
    }
}
proc get_pins {args} {
    set object [lindex [option $args -of_objects] 0]
    assert {[llength $object] > 0} "never query an empty object collection"
    if {[lsearch -exact $args -leaf] >= 0} {
        switch $::scenario {
            VCC { return VCC/P }
            logic { return logic/O }
            multiple { return {GND/G VCC/P} }
            undriven { return {} }
            default { return GND/G }
        }
    }
    set filter [option $args -filter]
    if {$filter eq {REF_PIN_NAME == Q}} { return [list $object/Q] }
    if {$filter eq {REF_PIN_NAME == C}} { return [list $object/C] }
    if {![regexp {CAS_IN_([A-Z_]+)_([AB])\*$} $filter -> group side]} {
        error "Unexpected pin filter: $filter"
    }
    set width [dict get {ADDR 23 BWE 9 DIN 72 DOUT 72 EN 1 RDACCESS 1 RDB_WR 1 SBITERR 1 DBITERR 1} $group]
    if {$::scenario eq "missing_pin" && $group eq "EN" && $side eq "A"} { return {} }
    set pins {}
    for {set i 0} {$i < $width} {incr i} { lappend pins [format {%s/CAS_IN_%s_%s[%d]} $object $group $side $i] }
    return $pins
}
proc get_nets {args} {
    if {$::scenario eq "query_error"} { error "Native query failed" }
    if {$::scenario eq "unconnected"} { return {} }
    return {segment1 segment2}
}
proc get_ports {args} { return [expr {$::scenario eq "external" ? "input_port" : {}}] }
proc get_clocks {args} { return clk_50_clkwiz }
proc all_fanout {args} {
    assert {[lrange $args 0 4] eq {-flat -endpoints_only -trace_arcs all -from}} "trace all arcs through buffers"
    set source [lindex [option $args -from] 0]
    switch -exact -- $source {
        i_dram_wrapper/fabric_ready_o_reg/Q {
            return {{gen_status_sync[2].i_sync/reg_q_reg[0]/D} {i_rstgen/i_rstgen_bypass/synch_regs_q_reg[0]/CLR}}
        }
        {gen_status_sync[2].i_sync/reg_q_reg[0]/Q} {
            if {$::scenario eq "bypass_stage"} { return i_vio/inst/input_reg/D }
            return {{gen_status_sync[2].i_sync/reg_q_reg[1]/D}}
        }
        {gen_status_sync[2].i_sync/reg_q_reg[1]/Q} {
            if {$::scenario eq "feedback"} { return {i_vio/inst/input_reg/D i_cheshire_soc/control_reg/D} }
            if {$::scenario eq "no_status_load"} { return {} }
            return i_vio/inst/input_reg/D
        }
        default { error "Unexpected fanout source: $source" }
    }
}
foreach forbidden {set_property set_msg_config create_waiver connect_net disconnect_net
    create_cell create_net read_xdc synth_design opt_design place_design route_design
    write_checkpoint write_bitstream} {
    proc $forbidden {args} { error "Forbidden mutation in warning audit" }
}
set scenarios {healthy FIRST MIDDLE LAST VCC logic multiple undriven unconnected external
    missing_pin missing_driver missing_uram unknown_order query_error missing_status
    bypass_stage feedback no_status_load}
foreach scenario $scenarios {
    set dir [file join $sandbox $scenario]
    set before [lsort [chan names]]
    set failed [catch {fpga_warning_details::write $dir} message]
    assert {$failed == ($scenario in {missing_driver missing_uram unknown_order query_error missing_status})} \
        "$scenario unexpected result: $message"
    assert {[lsort [chan names]] eq $before} "report closes on failure"
    set in [open [file join $dir warning_details.rpt] r]
    set report [read $in]; close $in
    assert {[string match *COLLECTION_COMPLETE=1* $report] != $failed} "no success marker on query errors"
    assert {[string match *MANUAL_REVIEW_REQUIRED=1* $report]} "collection never waives findings"
    if {!$failed} {
        set zero [expr {$scenario in {healthy FIRST MIDDLE LAST bypass_stage feedback no_status_load}}]
        assert {[string match *URAM_NON_GND_OR_MISSING_ITEMS=0* $report] == $zero} "non-ground is not silently accepted"
        set observer [expr {$scenario ni {bypass_stage feedback no_status_load}}]
        assert {[string match *VIO_TWO_STAGE_OBSERVATION_FANOUT_ONLY=1* $report] == $observer} "functional VIO feedback is reported"
        set pins [regexp -all -line {^CASCADE_PIN } $report]
        set expected [expr {$scenario in {MIDDLE LAST} ? 0 : ($scenario eq "missing_pin" ? 361 : 362)}]
        assert {$pins == $expected} "all cascade input bits counted, not bus groups"
    }
    assert {[catch {fpga_warning_details::write $dir}]} "never overwrite previous evidence"
    set in [open [file join $dir warning_details.rpt] r]
    assert {[read $in] eq $report} "failed repeat preserves report"
    close $in
    puts "PASS warning details $scenario"
}
puts "PASS: [llength $scenarios] warning detail scenarios (query fixtures only)"
