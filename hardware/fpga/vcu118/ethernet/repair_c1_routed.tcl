# One guarded, physical-only repair of the measured C1 FIFO CE paths.
namespace eval c1_repair {}
proc c1_repair::safe_driver {name type async protected} {
    return [expr {[string match {i_dram_wrapper/gen_cdc.i_axi_cdc_mig/*} $name] &&
        [regexp {^(LUT[1-6]|MUXF[7-9])$} $type] &&
        $async ni {1 true TRUE} && $protected ni {1 true TRUE}}]
}
proc c1_repair::targets {out} {
    set paths [get_timing_paths -quiet -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1]
    if {[llength $paths] != 205} {error "Expected the measured 205 failing endpoints, got [llength $paths]"}
    set clock [get_clocks -quiet mmcm_clkout0_1]
    if {[llength $clock] != 1} {error "Missing C1 clock"}
    # Vivado 2020.1 timing_path has no PATH_GROUP property. Prove scope using
    # the same supported -from/-to clock selection as the domain reports.
    set scoped [get_timing_paths -quiet -from $clock -to $clock -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1]
    if {[lsort [get_property ENDPOINT_PIN $paths]] ne [lsort [get_property ENDPOINT_PIN $scoped]]} {
        error "Failing endpoints are not exclusively C1 intra-clock paths"
    }
    set f [open [file join $out targets.tsv] w]
    puts $f "startpoint\tendpoint\tslack\tdriver\ttype\tnet\tloads"
    set code [catch {
        set nets {}
        foreach path $paths {
            set endpoint [get_property ENDPOINT_PIN $path]
            if {![string match {i_dram_wrapper/gen_cdc.i_axi_cdc_mig/*/CE} $endpoint]} {
                error "Unreviewed failure outside C1 FIFO CE logic: $endpoint"
            }
            set pattern [string map [list {[} {\[} {]} {\]}] $endpoint]
            set pin [get_pins -quiet $pattern]
            if {[llength $pin] != 1} {error "Missing/ambiguous endpoint pin: $endpoint"}
            set net [get_nets -quiet -of_objects $pin]
            if {[llength $net] != 1 || [get_property DONT_TOUCH $net] in {1 true TRUE}} {
                error "Missing/protected endpoint net: $endpoint"
            }
            set drivers [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}]
            set cells [get_cells -quiet -of_objects $drivers]
            if {[llength $cells] != 1} {error "Ambiguous CE driver: $endpoint"}
            set name [get_property NAME $cells]
            set type [get_property REF_NAME $cells]
            if {![safe_driver $name $type [get_property ASYNC_REG $cells] [get_property DONT_TOUCH $cells]]} {
                error "Refuse to replicate synchronizer/register/protected driver: $name / $type"
            }
            set loads [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}]
            puts $f [join [list [get_property STARTPOINT_PIN $path] $endpoint [get_property SLACK $path] $name $type [get_property NAME $net] [llength $loads]] "\t"]
            lappend nets $net
        }
        set nets [lsort -unique $nets]
    } result options]
    close $f
    if {$code} {return -options $options $result}
    return $nets
}
proc c1_repair::run {mode package out token reference tools} {
    if {$mode ne "impl_existing"} {error "Repair only supports an accepted routed checkpoint"}
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    set ::rebuild_test_mode true
    source [file join $package ethernet rebuild_mainrtl_v3.tcl]
    foreach library {common.tcl run_support.tcl} {
        uplevel #0 [list source [file join $package scripts $library]]
    }
    set f [open [file join $tools accepted_routed.txt] r]
    set checkpoint [string trim [read $f]]
    close $f
    fpga_run::nonempty $checkpoint
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    rebuild_stage $out opening_preserved_routed_netlist
    open_checkpoint $checkpoint
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        if {[report_route_status -boolean_check $check] != $expected} {error "Input route integrity failed: $check"}
    }
    rebuild_stage $out classify_all_205_endpoints
    report_timing -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1 -file [file join $out all_failing_setup.rpt]
    set nets [targets $out]
    if {![llength $nets]} {error "No safe combinational drivers selected"}
    puts "C1_REPAIR_COMBINATIONAL_NETS [llength $nets] $nets"
    rebuild_stage $out replicate_only_c1_combinational_ce_drivers
    phys_opt_design -force_replication_on_nets $nets
    write_checkpoint [file join $out replicated.dcp]
    if {![report_route_status -boolean_check ROUTED_FULLY]} {
        rebuild_stage $out repair_affected_routes
        route_design
    }
    global design_top
    # Save even a nonpassing outcome; never overwrite the accepted input.
    write_checkpoint [file join $out ${design_top}_routed.dcp]
    report_route_status -file [file join $out route_status.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    rebuild_domain_timing [file join $out routed_domains]
    rebuild_stage $out strict_routed_timing_gate
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        if {[report_route_status -boolean_check $check] != $expected} {error "Output route integrity failed: $check"}
    }
    fpga_run::require_timing [file join $out routed_gate]
    rebuild_stage $out routed_ready_for_audit
    close_design
}
if {![info exists ::c1_repair_test_mode]} {
    if {[catch {
        if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
        c1_repair::run {*}$argv
    } message]} {puts stderr $::errorInfo; exit 1}
    exit 0
}
