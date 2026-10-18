# Full ara_soc synthesis, adapted from the completed dc_ara_main_real flow.
# Run only through the explicit run command, from a sealed per-run directory.
proc stage {name} {
    set f [open dc.status w]
    puts $f "stage=$name"
    puts $f "updated_utc=[clock format [clock seconds] -gmt 1 -format %Y-%m-%dT%H:%M:%SZ]"
    close $f
    puts "DC_FLOW_STAGE=$name"
}
proc require_ok {script} {
    set result [uplevel 1 $script]
    if {!$result} {error "DC command failed: $script"}
}
proc checkpoint {name} {
    write -format ddc -hierarchy -output ../outputs/ara_soc_${name}.ddc
}
proc min_slack {paths} {
    if {![sizeof_collection $paths]} {return NA}
    set result Inf
    foreach value [get_attribute $paths slack] {if {$value < $result} {set result $value}}
    return $result
}
# Known installation-only missing-manual message is recorded, not suppressed.
set startup_manual_errors [get_message_info -occurrences CMD-025]
puts "DC_STARTUP_MANUAL_ERRORS=$startup_manual_errors"
if {[catch {
    source ../global_scripts/synopsys_dc.setup.gui
    source ../global_scripts/synopsys_dc.setup.env
    source ../global_scripts/synopsys_dc.setup.main
    stage ANALYZE
    set_svf ../outputs/ara_soc.svf
    define_design_lib WORK -path ./work
    set hdlin_check_no_latch true
    set compile_seqmap_propagate_constants false
    set compile_enable_register_merging false
    set compile_register_replication false
    set enable_recovery_removal_arcs true
    set report_default_significant_digits 6
    set_host_options -max_cores $GUI_MAX_CPU_NUM
    require_ok {analyze -format sverilog -vcs $GUI_VCS_OPTION}
    stage ELABORATE
    require_ok {elaborate ara_soc}
    current_design ara_soc
    stage LINK
    require_ok {link}
    require_ok {check_design}
    set_register_merging [current_design] false
    checkpoint gtech
    source ../local_scripts/ara_soc.sdc
    report_hierarchy -noleaf > ../reports/hierarchy_pre.rpt
    check_timing > ../reports/check_timing_pre.rpt
    check_design > ../reports/check_design_pre.rpt
    # Macro use and retained RCE hierarchy are visible before optimization.
    set macro_cells [get_cells -hier -filter {ref_name =~ TS1N28*}]
    set vrf_macros [get_cells -hier -filter {ref_name == TS1N28HPCPUHDSVTB16X64M1SWBSO}]
    set l2_macros [get_cells -hier -filter {ref_name == TS1N28HPCPSVTB8192X128M4SWBASO}]
    if {[sizeof_collection $vrf_macros] != 32 || [sizeof_collection $l2_macros] != 8} {
        error "Expected 32 VRF macros and 8 L2 macros for 4 lanes/VLEN1024/1MiB L2"
    }
    set f [open ../reports/macro_inventory.rpt w]
    foreach_in_collection c $macro_cells {puts $f "[get_object_name $c] [get_attribute $c ref_name]"}
    close $f
    set rce_cells [get_cells -hier -filter {ref_name =~ reduction_completion_engine*}]
    if {$RCE_EXPECT_ENGINE && ![sizeof_collection $rce_cells]} {error "RCE hierarchy missing"}
    if {!$RCE_EXPECT_ENGINE && [sizeof_collection $rce_cells]} {error "RCE unexpectedly enabled"}
    set shared_adds [get_cells -hier -filter {full_name =~ *i_shared_ordered_adder*gen_unit*i_add}]
    set local_adds [get_cells -hier -filter {full_name =~ *i_fpnew_ordered_fast}]
    set f [open ../reports/ordered_backend_inventory.rpt w]
    puts $f "shared_units=[sizeof_collection $shared_adds] expected=$RCE_EXPECT_SHARED_ORDERED"
    puts $f "lane_local_units=[sizeof_collection $local_adds] expected=$RCE_EXPECT_LOCAL_ORDERED"
    close $f
    if {[sizeof_collection $shared_adds] != $RCE_EXPECT_SHARED_ORDERED ||
        [sizeof_collection $local_adds] != $RCE_EXPECT_LOCAL_ORDERED} {
        error "Ordered backend topology differs from selected area profile"
    }
    if {$RCE_ELAB_ONLY} {
        stage ELABORATED
        puts DC_ELAB_COMPLETE
    } else {
        set_fix_multiple_port_nets -all -buffer_constants
        # Hold repair is opt-in in DC. Keep the original setup/hold constraints;
        # allow the mapper to insert data-path delay without worsening setup WNS.
        set_fix_hold [all_clocks]
        set_app_var verilogout_no_tri true
        set_cost_priority -delay
        set power_cg_module_naming_style CLKGATE_%e_%d
        set power_cg_cell_naming_style %c_clkgate_%n
        set power_cg_gated_clock_net_naming_style %c_gate_%n
        set_clock_gating_style -sequential latch \
            -positive_edge_logic integrated:$GUI_GATER_CLOCK_CELL \
            -control_point $GUI_GATER_CLOCK_CONTROL_POINT \
            -minimum_bitwidth $GUI_GATER_CLOCK_MIN_BITWIDTH \
            -setup $GUI_GATER_SETUP -num_stages $GUI_GATER_NUM_STAGES \
            -max_fanout $GUI_GATER_MAX_FANOUT
        set_leakage_optimization true
        set_dynamic_optimization true
        stage COMPILE
        require_ok {compile_ultra -no_seq_output_inversion -no_autoungroup -gate_clock}
        checkpoint mapped_checkpoint
        report_qor > ../reports/qor_before_incremental.rpt
        report_constraint -all_violators -nosplit > ../reports/violation_before_incremental.rpt
        stage INCREMENTAL_TIMING
        # Revisit mapped setup, hold and design-rule violations after the first
        # pass. Preserve hierarchy and the same clock-gating policy.
        require_ok {compile_ultra -incremental -no_seq_output_inversion -no_autoungroup -gate_clock}
        checkpoint timing_optimized
        stage REPORT
        define_name_rules verilog -target_bus_naming_style {%s[%d]} -case_insensitive
        change_names -rules verilog -hierarchy
        require_ok {check_design}
        set unmapped [get_cells -hier -filter {is_unmapped == true && is_hierarchical == false}]
        if {[sizeof_collection $unmapped]} {error "Unmapped leaf cells remain"}
        report_area -hierarchy > ../reports/area.rpt
        report_qor > ../reports/qor.rpt
        report_hierarchy -noleaf > ../reports/hierarchy.rpt
        report_constraint -all_violators -nosplit > ../reports/violation.rpt
        report_constraint -all_violators -max_delay -nosplit > ../reports/violation_setup.rpt
        report_constraint -all_violators -min_delay -nosplit > ../reports/violation_hold.rpt
        report_constraint -all_violators -max_transition -max_capacitance -max_fanout -nosplit \
            > ../reports/violation_design_rules.rpt
        report_clock -attributes > ../reports/clock_attributes.rpt
        report_clock_gating > ../reports/clock_gating.rpt
        check_design > ../reports/check_design.rpt
        check_timing > ../reports/check_timing.rpt
        report_timing -delay_type max -max_paths 100 -transition_time -input_pins -nets \
            > ../reports/timing_max.rpt
        report_timing -delay_type min -max_paths 100 -transition_time -input_pins -nets \
            > ../reports/timing_min.rpt
        set starts [all_registers -edge_triggered -output_pins]
        set ends [all_registers -edge_triggered -data_pins]
        report_timing -from $starts -to $ends -delay_type max -max_paths 50 \
            > ../reports/reg2reg_max.rpt
        # A SoC-wide worst path may hide the cost of a new mux or long Lane wire.
        # Keep paths crossing each relevant module boundary, including both its
        # input and return routes. Missing blocks are recorded, never fabricated.
        set block_index [open ../reports/reduction_path_inventory.rpt w]
        foreach {label pattern} {
            shared_ordered shared_ordered_adder*
            completion reduction_completion_engine*
            requester operand_requester*
            valu valu*
            vmfpu vmfpu*
            finalizer fp32_exact_reduction_finalize*
        } {
            set blocks [get_cells -hier -filter "ref_name =~ $pattern"]
            puts $block_index "$label instances=[sizeof_collection $blocks]"
            if {[sizeof_collection $blocks]} {
                set boundary [get_pins -of_objects $blocks]
                if {[sizeof_collection $boundary]} {
                    redirect ../reports/reduction_${label}_max.rpt {
                        report_timing -through $boundary -delay_type max -max_paths 10 \
                            -transition_time -input_pins -nets
                    }
                }
            }
        }
        close $block_index
        # No SAIF/VCD annotation: this is an explicitly vectorless estimate.
        report_power -hierarchy > ../reports/power_vectorless.rpt
        set f [open ../reports/physical_summary.rpt w]
        puts $f "scope=ara_soc_integrated"
        puts $f "profile=$RCE_PROFILE"
        puts $f "clock_period_ns=$RCE_CLOCK_PERIOD_NS"
        puts $f "setup_uncertainty_ns=[expr {.15 * $RCE_CLOCK_PERIOD_NS}]"
        puts $f "hold_uncertainty_ns=0.075"
        puts $f "hold_fix_enabled=1"
        puts $f "incremental_timing_passes=1"
        puts $f "total_cell_area=[get_attribute [current_design] area]"
        puts $f "worst_setup_slack_ns=[min_slack [get_timing_paths -delay_type max -max_paths 1]]"
        puts $f "worst_hold_slack_ns=[min_slack [get_timing_paths -delay_type min -max_paths 1]]"
        puts $f "worst_reg2reg_slack_ns=[min_slack [get_timing_paths -delay_type max -from $starts -to $ends -max_paths 1]]"
        puts $f "power=vectorless_not_workload_power"
        close $f
        # Keep hierarchy for Ara/RCE/Lane/SLDU attribution and downstream tools.
        write -format ddc -hierarchy -output ../outputs/ara_soc_dc.ddc
        write -format verilog -hierarchy -output ../outputs/ara_soc_dc.v
        write_sdc -version 1.8 ../outputs/ara_soc_dc.sdc
    }
    set_svf -off
    set errors [expr {[get_message_info -error_count] - $startup_manual_errors}]
    puts "DC_FLOW_ERROR_COUNT=$errors"
    if {$errors != 0} {error "DC reported errors; outputs are not accepted"}
    if {!$RCE_ELAB_ONLY} {stage COMPLETE; puts DC_FLOW_COMPLETE}
} failure]} {
    puts stderr "RCE_DC_FAILURE: $failure"
    stage FAILED
    exit 1
}
exit 0
