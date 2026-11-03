# Native command/API test, not a prediction of full-design timing closure.
set ::self_reference_test_mode true
source [file join [file dirname [info script]] .. ethernet repair_self_reference.tcl]
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
    set checkpoint [file join [pwd] probe_routed.dcp]
    if {[file exists $checkpoint]} {error "Do not overwrite the native probe"}
    write_checkpoint $checkpoint
    self_reference::optimize $checkpoint [pwd]
    close_project
    puts "PASS: native Vivado self-reference TimingClosure and Explore TNS cleanup"
} message]} {puts stderr $::errorInfo; exit 1}
exit 0
