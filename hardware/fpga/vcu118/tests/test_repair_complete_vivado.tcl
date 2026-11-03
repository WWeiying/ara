# Exercise actual 2020.1 post-route optimization and property queries on a
# small routed design before opening the full multi-million-cell checkpoint.
set ::complete_repair_test_mode true
source [file join [file dirname [info script]] .. ethernet repair_complete_routed.tcl]
if {[catch {
    create_project -in_memory -part xcvu9p-flga2104-2L-e
    set_param general.maxThreads 2
    read_verilog [file join [file dirname [info script]] complete_repair_probe.v]
    synth_design -top complete_repair_probe -part xcvu9p-flga2104-2L-e
    create_clock -period 3.333 [get_ports clk]
    opt_design
    place_design
    route_design
    complete_repair::route_integrity
    if {[llength [complete_repair::async_signature]] != 2} {error "Missing real synchronizer objects"}
    complete_repair::optimize
    complete_repair::route_integrity
    close_project
    puts "PASS: real Vivado post-route AggressiveExplore and invariant checks"
} message]} {puts stderr $::errorInfo; exit 1}
exit 0
