# Physical-only successor to the failed whole-design RuntimeOptimized reuse.
# Use the accepted current opt netlist, not any reference functional netlist.
namespace eval selective_reuse {}
proc selective_reuse::roots {} {
    return {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2}
}
proc selective_reuse::capture_ddr_clocks {} {
    set plan {}
    set used {}
    foreach root [roots] channel {c1 c2} {
        set name $root/gen_channel_${channel}.i_dram/inst/u_ddr4_infrastructure/u_bufg_inst
        set cell [get_cells -quiet -hier -filter [list NAME == $name]]
        if {[llength $cell] != 1} {
            # The routed reference eliminated C1's redundant ui-clock buffer;
            # it still has C2's source named in the current placer failure.
            if {$channel eq "c1" && [llength $cell] == 0} {
                puts "REFERENCE_C1_UI_BUFFER_ABSENT no C1 anchor imported"
                continue
            }
            set candidates [get_cells -quiet -hier -filter {REF_NAME =~ BUFG* && NAME =~ *u_ddr4_infrastructure*}]
            puts "REFERENCE_DDR_CLOCK_CANDIDATES $candidates"
            error "Missing reference DDR clock: $name"
        }
        set type [get_property REF_NAME $cell]
        set loc [get_property LOC $cell]
        set bel [get_property BEL $cell]
        if {![string match BUFG* $type] || $loc eq "" || $bel eq "" || $loc in $used} {
            error "Invalid reference DDR clock placement: $name $type $loc $bel"
        }
        lappend used $loc
        lappend plan [list $name $type $loc $bel]
        puts "REFERENCE_DDR_CLOCK [join [lindex $plan end] { }]"
    }
    return $plan
}
proc selective_reuse::restore_ddr_clocks {plan out} {
    set f [open [file join $out ddr_clock_anchors.tsv] w]
    set code [catch {
        puts $f "cell\tprimitive\tlocation\tbel"
        foreach row $plan {
            lassign $row name type loc bel
            set cell [get_cells -quiet -hier -filter [list NAME == $name]]
            if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne $type} {
                error "Current DDR clock differs from reviewed reference: $name"
            }
            set current [get_property LOC $cell]
            if {[get_property IS_LOC_FIXED $cell] && $current ne $loc} {
                error "Conflicting fixed DDR clock location: $name $current versus $loc"
            }
            set_property LOC $loc $cell
            set_property BEL $bel $cell
            set_property IS_LOC_FIXED true $cell
            if {[get_property LOC $cell] ne $loc || [get_property BEL $cell] ne $bel} {
                error "DDR clock anchor did not apply: $name"
            }
            puts $f [join $row "\t"]
            puts "DDR_CLOCK_ANCHORED [join $row { }]"
        }
    } result options]
    close $f
    if {$code} {return -options $options $result}
}
proc selective_reuse::check_route {out label} {
    set full [report_route_status -boolean_check ROUTED_FULLY]
    set errors [report_route_status -boolean_check ERRORS_IN_ROUTES]
    if {![string is boolean -strict $full] ||
        ![string is boolean -strict $errors] || !$full || $errors} {
        # Retain the failure before reporting; never attempt bitgen or silently
        # spend another full routing pass on an illegal route.
        write_checkpoint [file join $out ${label}_illegal.dcp]
        report_route_status -file [file join $out ${label}_route_status.rpt]
        error "Illegal $label route: ROUTED_FULLY=$full ERRORS_IN_ROUTES=$errors"
    }
    report_route_status -file [file join $out ${label}_route_status.rpt]
}
proc selective_reuse::run {mode package out token reference tools} {
    if {$mode ne "impl_existing" || ![regexp {^[0-9a-f]{12}$} $token]} {
        error "Selective recovery requires an accepted synthesis and impl_existing"
    }
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    set ::rebuild_test_mode true
    source [file join $package ethernet rebuild_mainrtl_v3.tcl]
    foreach library {common.tcl run_support.tcl} {
        uplevel #0 [list source [file join $package scripts $library]]
    }
    global design_top max_threads
    set f [open [file join $tools accepted_opt.txt] r]
    set optimized [string trim [read $f]]
    close $f
    fpga_run::nonempty $optimized
    fpga_run::nonempty $reference
    set_param general.maxThreads $max_threads
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    rebuild_stage $out capture_reviewed_ddr_clock_locations
    open_checkpoint $reference
    set clock_plan [capture_ddr_clocks]
    close_design
    # The optimized checkpoint already contains both successfully synthesized
    # DDR PHYs and the reviewed floorplan, but no incremental reference data.
    rebuild_stage $out open_accepted_floorplanned_opt
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    open_checkpoint $optimized
    # NAME identifies Vivado's design container, not the checkpoint's RTL top.
    # The launcher verifies dcp.xml Top and the pinned checkpoint hash. Retain
    # independent device and structural checks after opening the netlist.
    puts "OPENED_DESIGN_CONTAINER [get_property NAME [current_design]]"
    if {[get_property PART [current_design]] ne "xcvu9p-flga2104-2L-e"} {
        error "Unexpected optimized device"
    }
    if {[llength [get_cells -quiet i_cheshire_soc]] != 1} {
        error "Missing current compute hierarchy"
    }
    set objects {}
    foreach name [roots] {
        set object [get_cells -quiet $name]
        if {[llength $object] != 1} {error "Missing infrastructure root: $name"}
        lappend objects $object
    }
    # Exercise the real property APIs before the expensive incremental match;
    # reapply afterwards because reference import may update placement data.
    rebuild_stage $out prevalidate_ddr_clock_anchors
    restore_ddr_clocks $clock_plan $out
    # Deliberately exclude the entire changed compute/SoC hierarchy, including
    # QBS and VLSU. Do not force old placement or old routes in the hot regions.
    rebuild_stage $out infrastructure_only_reference_reuse
    read_checkpoint -incremental $reference -reuse_objects $objects
    rebuild_stage $out restore_ddr_clock_anchors
    restore_ddr_clocks $clock_plan $out
    report_incremental_reuse -file [file join $out reuse_before.rpt]
    rebuild_stage $out compute_replacement
    place_design
    write_checkpoint [file join $out placed.dcp]
    rebuild_domain_timing [file join $out placed_domains]
    rebuild_stage $out pre_route_fanout_optimization
    phys_opt_design -directive AggressiveFanoutOpt
    rebuild_stage $out routing
    route_design
    check_route $out first
    rebuild_stage $out post_route_physical_optimization
    phys_opt_design -directive Explore
    if {![report_route_status -boolean_check ROUTED_FULLY]} {route_design}
    check_route $out final
    write_checkpoint [file join $out ${design_top}_routed.dcp]
    report_incremental_reuse -file [file join $out reuse_after.rpt]
    rebuild_domain_timing [file join $out routed_domains]
    rebuild_stage $out routed_timing_gate
    fpga_run::require_timing [file join $out routed_gate]
    rebuild_stage $out routed_ready_for_audit
    close_design
}
if {![info exists ::selective_reuse_test_mode]} {
    if {[catch {
        if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
        selective_reuse::run {*}$argv
    } message]} {
        puts stderr $::errorInfo
        exit 1
    }
    exit 0
}
