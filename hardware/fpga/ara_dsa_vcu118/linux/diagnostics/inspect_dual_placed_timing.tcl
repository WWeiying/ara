# Read-only timing diagnosis of the preserved placement, not routed signoff.
if {[llength $argv] ni {2 3}} {error "Expected checkpoint output ?inventory_only?"}
lassign $argv checkpoint out mode
if {$mode ni {{} inventory_only}} {error "Unknown report mode"}
file mkdir $out
proc stage {name} {
    global out
    set f [open [file join $out stage.txt] w]
    puts $f $name
    close $f
    puts "TIMING_INSPECT $name"
    flush stdout
}
if {[catch {
    set_param general.maxThreads 8
    stage open_placed_checkpoint
    open_checkpoint $checkpoint
    if {$mode ne "inventory_only"} {
    stage timing_summary
    report_timing_summary -delay_type min_max -max_paths 20 -report_unconstrained \
        -file [file join $out timing_summary.rpt]
    stage setup_paths
    report_timing -delay_type max -slack_lesser_than 0 -max_paths 200 -nworst 1 \
        -path_type full_clock_expanded -input_pins -file [file join $out setup_paths.rpt]
    stage hold_paths
    report_timing -delay_type min -slack_lesser_than 0 -max_paths 50 -nworst 1 \
        -path_type full_clock_expanded -file [file join $out hold_paths.rpt]
    }
    stage endpoint_inventory
    set f [open [file join $out setup_endpoints.tsv] w]
    puts $f "slack\tstartpoint\tendpoint\tstart_clock\tend_clock\tgroup\tlogic_levels\tdatapath_delay\trequirement"
    foreach path [get_timing_paths -quiet -delay_type max -slack_lesser_than 0 -max_paths 50000 -nworst 1] {
        set row {}
        foreach prop {SLACK STARTPOINT_PIN ENDPOINT_PIN STARTPOINT_CLOCK ENDPOINT_CLOCK} {
            lappend row [get_property $prop $path]
        }
        # Vivado 2020.1 does not expose PATH_GROUP on timing_path objects.
        # Optional columns must not abort the authoritative endpoint export.
        set properties [list_property $path]
        foreach prop {PATH_GROUP LOGIC_LEVELS DATAPATH_DELAY REQUIREMENT} {
            if {$prop in $properties} {lappend row [get_property $prop $path]} else {lappend row {}}
        }
        puts $f [join $row "\t"]
    }
    close $f
    stage physical_inventory
    set f [open [file join $out physical_inventory.tsv] w]
    puts $f "component\tcells\tslrs\tclock_regions"
    foreach pattern {
        i_dram_wrapper/i_ui_rstgen/*
        gen_ddr2.i_dram_wrapper_c2/i_ui_rstgen/*
        i_dram_wrapper/gen_ethernet.i_eth_shared_ddr/*
        i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/mac/inst/pcs_pma/inst/pcs_pma_block_i/gen_lvds_transceiver*
        i_dram_wrapper/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/*
        gen_ddr2.i_dram_wrapper_c2/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/*
    } {
        set cells [get_cells -quiet -hierarchical -filter "NAME =~ $pattern && IS_PRIMITIVE"]
        if {![llength $cells]} {error "Physical inventory empty: $pattern"}
        set sites [get_sites -quiet -of_objects $cells]
        puts $f [join [list $pattern [llength $cells] [get_slrs -quiet -of_objects $sites] \
            [get_clock_regions -quiet -of_objects $sites]] "\t"]
    }
    close $f
    stage clock_and_constraint_reports
    report_clocks -file [file join $out clocks.rpt]
    report_clock_interaction -file [file join $out clock_interaction.rpt]
    report_exceptions -file [file join $out exceptions.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    report_utilization -hierarchical -file [file join $out utilization.rpt]
    stage complete_placed_estimates_not_routed_signoff
    close_design
} message]} {
    puts stderr $::errorInfo
    stage failed
    exit 1
}
exit 0
