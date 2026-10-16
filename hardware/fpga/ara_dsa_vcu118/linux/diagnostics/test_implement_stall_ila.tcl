set ::stall_implementation_test 1
source [file join [file dirname [info script]] implement_stall_ila.tcl]
rename source real_source
proc source {path} {
    if {[file tail $path] ni {common.tcl run_support.tcl}} { error "Unexpected source" }
    set ::board_part xilinx.com:vcu118:part0:2.4
    set ::fpga_part xcvu9p-flga2104-2L-e
}
namespace eval fpga_run {}
proc set_param {args} {}
proc get_param {args} { return {} }
proc get_board_parts {args} { return $::board_available }
proc set_msg_config {args} {
    if {[lindex $args end] ne "ERROR"} { error "Do not relax diagnostics" }
}
proc current_project {} { return project }
proc open_checkpoint {path} { lappend ::events open }
proc get_debug_cores {args} { return i_stall_ila }
proc get_debug_ports {args} { return i_stall_ila/probe0 }
proc set_property {property value object} {
    if {$property ne "ALL_PROBE_SAME_MU_CNT" || $value != 2 || $object ne "i_stall_ila"} {
        error "Unexpected design modification"
    }
    set ::mu $value
}
proc get_property {property object} {
    switch -- $property {
        PORT_WIDTH { return $::width }
        C_DATA_DEPTH { return 1024 }
        C_INPUT_PIPE_STAGES { return 1 }
        C_ADV_TRIGGER { return true }
        ALL_PROBE_SAME_MU_CNT { return $::mu }
        BOARD_PART { return $::board_part }
        PART { return $::actual_part }
        default { error "Unexpected property: $property" }
    }
}
proc opt_design {} { lappend ::events opt }
proc get_cells {args} { return $::blackboxes }
proc write_checkpoint {path} { lappend ::events [file tail $path] }
proc read_checkpoint {flag path} {
    if {$flag ne "-incremental"} { error "Must use physical reference only" }
    lappend ::events reference
}
proc report_incremental_reuse {args} {}
proc place_design {} { lappend ::events place }
proc route_design {} { lappend ::events route }
proc report_route_status {args} {
    if {[lindex $args 0] eq "-file"} { return }
    if {[lindex $args 1] eq "ROUTED_FULLY"} { return $::routed }
    return 0
}
proc require_no_multiple_drivers {dir} { lappend ::events drivers }
proc write_reports {dir reject} {
    if {!$reject} { error "Loops must be rejected" }
    lappend ::events reports
}
proc fpga_run::require_timing {dir} {
    lappend ::events timing
    if {!$::timing} { error "Timing violation" }
}
proc close_design {} { lappend ::events close }
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error $message }
}
set channel [file tempfile root]
close $channel
file delete $root
file mkdir $root
foreach name {prepared reference} {
    close [open [file join $root $name.dcp] w]
}
try {
    foreach scenario {pass width blackbox route timing missing_board wrong_part invalid_mu} {
        set ::events {}
        set ::width 579
        set ::blackboxes {}
        set ::routed 1
        set ::timing 1
        set ::mu 1
        set ::board_available xilinx.com:vcu118:part0:2.4
        set ::actual_part xcvu9p-flga2104-2L-e
        switch -- $scenario {
            width { set ::width 578 }
            blackbox { set ::blackboxes missing_ip }
            route { set ::routed 0 }
            timing { set ::timing 0 }
            missing_board { set ::board_available {} }
            wrong_part { set ::actual_part wrong }
            invalid_mu { set ::mu 0 }
        }
        set out [file join $root $scenario]
        set result [catch {
            stall_implementation::run [file join $root prepared.dcp] \
                [file join $root reference.dcp] $root $out 579
        } message]
        assert {$result == ($scenario ne "pass")} "Wrong outcome: $scenario $message"
        if {$scenario eq "pass"} {
            assert {$::mu == 2} "Advanced trigger must have two match units"
            assert {$::events eq {open opt optimized.dcp reference place placed.dcp route routed.dcp drivers reports timing close}} "Wrong implementation order"
            set f [open [file join $out stage.txt]]
            set stage [string trim [read $f]]
            close $f
            assert {$stage eq "timing_passed_requires_full_audit"} "Must require audit"
        } else {
            assert {[lsearch -exact $::events close] == -1} "Failure accepted"
        }
    }
    puts "STALL_IMPLEMENTATION_FLOW_TESTS_PASS (mock flow, not hardware validation)"
} finally {
    file delete -force $root
}
