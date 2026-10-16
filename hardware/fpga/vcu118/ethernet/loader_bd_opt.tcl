# Early implementation audit of the standalone loader; does not route or bitgen.
namespace eval loader_opt {
    proc run {output {tag ""}} {
        if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
        if {![regexp {^_[A-Za-z0-9_]+$|^$} $tag]} { error "Invalid output tag" }
        set project [file join $output project eth_loader_bd.xpr]
        if {![file isfile $project]} { error "Missing project: $project" }
        open_project $project
        if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {
            error "Synthesis is not complete"
        }
        open_run synth_1
        set hub [get_debug_cores -quiet dbg_hub]
        if {[llength $hub] != 1} { error "Expected one registered dbg_hub" }
        set other_blackboxes {}
        foreach cell [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}] {
            if {[get_property NAME $cell] ne "dbg_hub"} { lappend other_blackboxes $cell }
        }
        if {[llength $other_blackboxes]} {
            error "Unresolved IP before opt_design: $other_blackboxes"
        }
        set cpu_pin [get_pins -quiet loader_bd_i/mb/Clk]
        if {[llength $cpu_pin] != 1} { error "Missing MicroBlaze clock pin" }
        set clock_net [get_nets -quiet -of_objects $cpu_pin]
        if {[llength $clock_net] != 1} { error "Missing MicroBlaze clock net" }
        if {[llength [get_nets -quiet -of_objects [get_pins -quiet dbg_hub/clk]]]} {
            disconnect_debug_port dbg_hub/clk
        }
        connect_debug_port dbg_hub/clk $clock_net
        set_property C_CLK_INPUT_FREQ_HZ 100000000 $hub
        set_property C_ENABLE_CLK_DIVIDER false $hub
        opt_design
        set blackboxes [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}]
        if {[llength $blackboxes]} { error "Blackboxes after opt_design: $blackboxes" }
        set channel [open [file join $output opt_report${tag}.txt] {WRONLY CREAT EXCL}]
        puts $channel "OPT_COMPLETE BLACKBOXES=0 DEBUG_CLOCK=$clock_net"
        puts $channel "NOT_PLACED_NOT_ROUTED_NOT_BITGEN"
        close $channel
        report_utilization -file [file join $output utilization_opt${tag}.rpt]
        report_timing_summary -delay_type min_max -report_unconstrained \
            -file [file join $output timing_opt${tag}.rpt]
        report_cdc -details -file [file join $output cdc_opt${tag}.rpt]
        report_drc -file [file join $output drc_opt${tag}.rpt]
        write_checkpoint [file join $output loader_opt${tag}.dcp]
        close_project
        puts "LOADER_OPT_COMPLETE $output"
    }
}

if {[llength $argv] < 1 || [llength $argv] > 2} {
    error "Usage: loader_bd_opt.tcl OUTPUT ?OUTPUT_TAG?"
}
if {[catch {loader_opt::run {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
