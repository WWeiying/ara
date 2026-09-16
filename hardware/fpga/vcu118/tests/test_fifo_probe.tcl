# Test orchestration/fail-closed behavior, not Vivado's synthesis algorithms.
set package [file normalize [lindex $argv 0]]
set directory [file normalize [lindex $argv 1]]
file mkdir $directory
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc create_project {args} {
    assert {$args eq {-in_memory -part xcvu9p-flga2104-2L-e}} "isolated, same target"
}
proc set_param {args} {}
proc current_fileset {} { return sources_1 }
proc set_property {args} {}
proc read_verilog {args} {
    assert {[file isfile [lindex $args end]]} "missing probe RTL"
    lappend ::inputs [lindex $args end]
}
proc set_msg_config {args} { lappend ::messages $args }
proc synth_design {args} {
    assert {$args eq {-top fifo_probe -part xcvu9p-flga2104-2L-e -mode out_of_context -flatten_hierarchy none}} "same synthesis mapping mode"
    if {$::scenario eq "synth_error"} { error "simulated synthesis failure" }
}
proc report_drc {args} {
    assert {[lrange $args 0 3] eq {-checks {MDRV-1 LUTLP-1} -name fifo_probe}} "structural checks required"
}
proc get_drc_violations {args} {
    return [expr {$::scenario eq "multi_driver" ? "MDRV-1#1" : ""}]
}
proc get_cells {args} {
    set filter [lindex $args end]
    set count [expr {[string match {NAME =~ i_r/*} $filter] ? 288 : 320}]
    # The real failing netlist inserts an i_1 hierarchy beneath the FIFO.
    foreach prefix {i_w i_w_const i_r} {
        foreach side {src dst} gen {write read} {
            set pattern $prefix/i_$side/*gen_fpga_${gen}*select_q_reg*
            if {[string first $pattern $filter] >= 0} {
                assert {[string match $pattern $prefix/i_$side/i_1/gen_fpga_${gen}.select_q_reg]} "generated hierarchy must match"
            }
        }
    }
    if {$::scenario eq "selector_missing"} { incr count -1 }
    return [lrepeat $count ff]
}
proc report_utilization {args} {}
proc write_checkpoint {args} { set ::checkpoint 1 }
proc close_project {} { set ::closed 1 }
rename exit real_exit
proc exit {code} { set ::exit_code $code; return -code error -errorcode PROBE_EXIT "probe exit" }
foreach scenario {healthy synth_error multi_driver selector_missing} {
    set inputs {}; set messages {}; set checkpoint 0; set closed 0; set exit_code -1
    set argv [list $directory]
    catch {source [file join $package scripts check_fifo.tcl]} reason options
    assert {[dict get $options -errorcode] eq "PROBE_EXIT"} "must exit predictably: $reason"
    assert {$exit_code == ($scenario ne "healthy")} "$scenario must fail closed"
    assert {[llength $inputs] == 8} "probe uses the actual FIFO and AXI source"
    assert {$messages eq {{-id {Synth 8-6858} -new_severity ERROR} {-id {Synth 8-6859} -new_severity ERROR}}} "do not accept driver substitution"
    assert {$checkpoint == ($scenario eq "healthy")} "no accepted checkpoint on failure"
    assert {$closed == ($scenario eq "healthy")} "close successful isolated project"
    puts "PASS FIFO probe $scenario"
}
