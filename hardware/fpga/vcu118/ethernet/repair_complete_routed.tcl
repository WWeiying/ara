# Successor to the CE-only experiment: review every endpoint and use the
# vendor's post-route optimizer for both control and data paths.
namespace eval complete_repair {}
proc complete_repair::family {endpoint} {
    foreach {prefix label} {
        i_dram_wrapper/gen_cdc.i_axi_cdc_mig/ c1_fifo
        i_dram_wrapper/gen_ethernet.i_eth_shared_ddr/ ethernet_shared_ddr
        i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/ddr_fabric/ ethernet_fabric
        i_dram_wrapper/gen_channel_c1.i_dram/inst/u_ddr4_mem_intfc/u_ddr_cal_top/u_ddr_cal/u_ddr_cal_addr_decode/ mig_calibration
    } {
        if {[string first $prefix $endpoint] == 0 && [file tail $endpoint] in {CE D}} {
            return $label
        }
    }
    error "Unreviewed endpoint: $endpoint"
}
proc complete_repair::same_endpoints {expected actual label} {
    if {![llength $expected] || [llength [lsort -unique $expected]] != [llength $expected] ||
        [lsort $expected] ne [lsort $actual]} {
        error "Endpoint inventory mismatch: $label"
    }
}
proc complete_repair::review {manifest out} {
    set f [open $manifest r]
    set expected [split [string trim [read $f]] \n]
    close $f
    set paths [get_timing_paths -quiet -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1]
    same_endpoints $expected [get_property ENDPOINT_PIN $paths] preserved_routed_input
    set clock [get_clocks -quiet mmcm_clkout0_1]
    if {[llength $clock] != 1} {error "Missing/ambiguous C1 clock"}
    set scoped [get_timing_paths -quiet -from $clock -to $clock -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1]
    same_endpoints $expected [get_property ENDPOINT_PIN $scoped] c1_intra_clock
    set f [open [file join $out reviewed_endpoints.tsv] w]
    puts $f "family\tpin\tslack\tstartpoint\tendpoint"
    set counts [dict create]
    set code [catch {
        foreach path $paths {
            set endpoint [get_property ENDPOINT_PIN $path]
            set group [family $endpoint]
            set pin [file tail $endpoint]
            set slack [get_property SLACK $path]
            if {![string is double -strict $slack] || $slack >= 0} {error "Invalid failing-path slack"}
            dict incr counts $group/$pin
            puts $f [join [list $group $pin $slack [get_property STARTPOINT_PIN $path] $endpoint] "\t"]
        }
    } message options]
    close $f
    if {$code} {return -options $options $message}
    puts "REVIEWED_ENDPOINTS [llength $paths] GROUPS $counts"
}
proc complete_repair::async_signature {} {
    set rows {}
    foreach cell [get_cells -quiet -hierarchical -filter {ASYNC_REG == TRUE}] {
        lappend rows [list [get_property NAME $cell] [get_property REF_NAME $cell]]
    }
    return [lsort $rows]
}
proc complete_repair::clock_signature {} {
    set rows {}
    foreach clock [get_clocks -quiet *] {
        lappend rows [list [get_property NAME $clock] [get_property PERIOD $clock] [get_property WAVEFORM $clock]]
    }
    return [lsort $rows]
}
proc complete_repair::optimize {} {
    set sync_before [async_signature]
    set clocks_before [clock_signature]
    # Explicit net replication is not used: data paths include low-fanout
    # placement/routing bottlenecks and synchronizer-driven vendor logic.
    phys_opt_design -directive AggressiveExplore
    if {[async_signature] ne $sync_before} {error "ASYNC_REG inventory changed; no release permitted"}
    if {[clock_signature] ne $clocks_before} {error "Clock definitions changed; no release permitted"}
    puts "POSTROUTE_INVARIANTS PASS: ASYNC_REG inventory and clock definitions retained"
}
proc complete_repair::route_integrity {} {
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        set value [report_route_status -boolean_check $check]
        if {![string is boolean -strict $value] || [expr {!!$value}] != $expected} {
            error "Route integrity failed: $check=$value"
        }
    }
}
proc complete_repair::run {mode package out token reference tools} {
    if {$mode ne "impl_existing"} {error "Only the preserved routed input is supported"}
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
    route_integrity
    rebuild_stage $out review_complete_endpoint_inventory
    review [file join $tools reviewed_endpoints.txt] $out
    rebuild_stage $out postroute_aggressive_explore
    optimize
    # Preserve the result before any lengthy report or acceptance check.
    write_checkpoint [file join $out post_phys_opt.dcp]
    if {![report_route_status -boolean_check ROUTED_FULLY]} {
        rebuild_stage $out repair_affected_routes
        route_design
    }
    global design_top
    write_checkpoint [file join $out ${design_top}_routed.dcp]
    rebuild_stage $out strict_routed_acceptance
    report_route_status -file [file join $out route_status.rpt]
    route_integrity
    report_timing -delay_type max -slack_lesser_than 0 -max_paths 4096 -nworst 1 -file [file join $out remaining_setup.rpt]
    rebuild_domain_timing [file join $out routed_domains]
    report_bus_skew -file [file join $out bus_skew.rpt]
    fpga_run::require_timing [file join $out routed_gate]
    rebuild_stage $out routed_ready_for_audit
    close_design
}
if {![info exists ::complete_repair_test_mode]} {
    if {[catch {
        if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
        complete_repair::run {*}$argv
    } message]} {puts stderr $::errorInfo; exit 1}
    exit 0
}
