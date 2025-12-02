set svf_file_tail 0
set cur_shell_run_path  [pwd]
set svf_file $GUI_DESIGN_NAME.svf
while {[file isfile $svf_file]} {
        incr svf_file_tail 1
        set svf_file $GUI_DESIGN_NAME.svf.$svf_file_tail
}
set_svf $svf_file

file delete -force work
define_design_lib WORK -path ./work
set starttime [clock seconds]
#set alib_library_analysis_path $ALIB_LIB_PATH
set hdlin_check_no_latch true
#set hdlin_preserve_sequential true
#set hdlin_report_inferred_modules true
set compile_seqmap_propagate_constants false
#set compile_delete_unloaded_sequential_cells false
set compile_enable_register_merging false
set compile_register_replication false
set enable_recovery_removal_arcs true
set report_default_significant_digits 3

if { !$GUI_UNGROUP } {
        set compile_ultra_hier_opt      " -no_autoungroup"
        set hierarchy_opt               "-hierarchy"
}

## read verilog netlist
if { $GUI_BLOCK_ABSTRACTION_DESIGNS != ""} {
        set_top_implementation_options -block_references $GUI_BLOCK_ABSTRACTION_DESIGNS
}

if {$GUI_VCS_OPTION != ""} {
        analyze -format sverilog -vcs $GUI_VCS_OPTION
        elaborate $GUI_DESIGN_NAME
} else {
        source $GUI_RTL_ORDER_FILE
        analyze -format sverilog $GUI_RTL_FILE
        elaborate $GUI_DESIGN_NAME
}

#user defined
#set_dont_touch to keep sram as black boxes
#set_dont_touch [get_designs TS1N28HPCPSVTB8192X128M4SWBASO]
#set_dont_touch [get_designs TS1N28HPCPUHDSVTB16X64M1SWBSO]
#set_dont_touch [get_designs TS1N28HPCPUHDSVTB64X128M4SWBSO]
#set_dont_touch [get_designs TS1N28HPCPUHDSVTB64X256M1SWBSO]
#set_dont_touch [get_designs TS1N28HPCPUHDSVTB64X48M4SWBSO]

if { $GUI_BLOCK_ABSTRACTION_DESIGNS != ""} {
        remove_design -hierarchy $GUI_BLOCK_ABSTRACTION_DESIGNS
}
if { $GUI_DDC_FILE != ""} {
        read_ddc $GUI_DDC_FILE
}
puts $GUI_VCS_OPTION
current_design $GUI_DESIGN_NAME

if { ![link] } {
        echo "Linking error!"
        exit; #Exits DC if a serious linking problem is encountered
}
if { $GUI_BLOCK_ABSTRACTION_DESIGNS != ""} {
        report_top_implementation_options > ../reports/top_implementation_options.rpt
        report_block_abstraction > ../reports/top_implementation_options.rpt
}

## set dont merge DFF
set_register_merging [current_design] false

report_dont_touch > ../reports/dont_touch.rpt

# create Milkyway
if { $GUI_DCG_MODE } {
        if { [file exists ../$GUI_DESIGN_NAME.mdb] } {
                puts "The specified DCG milkyway database is already existing. It will be renamed first......"
                file delete -force ../$GUI_DESIGN_NAME.mdb_bak
                file rename -force ../$GUI_DESIGN_NAME.mdb ../$GUI_DESIGN_NAME.mdb_bak
        }

        if { $MILKYWAY_EXTEND_LAYER } {
                extend_mw_layers
        }

        create_mw_lib -technology $MILKYWAY_TECH ../$GUI_DESIGN_NAME.mdb
        set_mw_lib_reference -mw_reference_library $milkyway_library ../$GUI_DESIGN_NAME.mdb
        open_mw_lib ../$GUI_DESIGN_NAME.mdb
}


eval write -format ddc -output ../outputs/${GUI_DESIGN_NAME}_dc_gtech.ddc $hierarchy_opt

## constrain
if { $GUI_SDC_FILE != "" } {
        foreach constraint_file $GUI_SDC_FILE { source -echo -verbose $constraint_file }
} else {
        puts "ADS Info: Cann't find any timing constraint files."
        puts "ADS Info: please finish timing constraint files as ref.sdc in scripts directory."
        exit;
}

## ungroup
if { $GUI_UNGROUP } {
        ungroup -all -flatten
} else {
        set ungroup_list ""
        if { $GUI_UNGROUP_FILE != "" } {
                set F [open $GUI_UNGROUP_FILE r]
                while {![eof $F]} {
                        [gets $F line]
                        if { [regexp {^#} $line] || ![regexp {\S} $line] } { continue }
                        regexp {(\S+)\s+(\S+)} $line total cellname instancename
                        lappend ungroup_list $line
                }
                close $F
                foreach one_sub $ungroup_list {
                        set_dont_touch [get_cells -hierarchical -filter "ref_name==$one_sub"]
                }
                ungroup -flatten -all
                foreach one_sub $ungroup_list {
                        remove_attribute [get_cells -hierarchical -filter "ref_name==$one_sub"] dont_touch
                        ungroup -flatten -start_level 2 [get_cells -hierarchical -filter "ref_name==$one_sub"]
                }
        }
}
report_hierarchy -noleaf > ../reports/hierarchy.rpt

## Icc dp flow (topographical mode)
if { $GUI_DCG_MODE } {
        set_ignored_layers -min_routing_layer $GUI_MIN_ROUTE_LAYER -max_routing_layer $GUI_MAX_ROUTE_LAYER
        if { [file isfile $GUI_DEF_FILE] } {
                extract_physical_constraints $GUI_DEF_FILE
        }
        if { $GUI_DP_FLOW } {
                eval compile_ultra -no_seq_output_inversion $compile_ultra_hier_opt
                start_icc_dp -f ../global_scripts/icc_floorplan.tcl
                extract_physical_constraints ../outputs/${GUI_DESIGN_NAME}_dp.def
        }
}

## for clock gating opt
if { $GUI_CLOCK_GATE } {
        set power_cg_module_naming_style CLKGATE_%e_%d
        set power_cg_cell_naming_style %c_clkgate_%n
        set power_cg_gated_clock_net_naming_style %c_gate_%n
        set ckgt_cmd "set_clock_gating_style -sequential latch "
        append ckgt_cmd "-${GUI_GATER_CLOCK_TYPE}_edge_logic {integrated:$GUI_GATER_CLOCK_CELL} "
        append ckgt_cmd "-control_point $GUI_GATER_CLOCK_CONTROL_POINT "
        if { $GUI_GATER_CLOCK_CONTROL_SIGNAL != "none" } {
                append ckgt_cmd "-control_signal $GUI_GATER_CLOCK_CONTROL_SIGNAL "
        }
        append ckgt_cmd "-minimum_bitwidth $GUI_GATER_CLOCK_MIN_BITWIDTH "
        append ckgt_cmd "-setup $GUI_GATER_SETUP "
        append ckgt_cmd "-num_stages $GUI_GATER_NUM_STAGES "
        append ckgt_cmd "-max_fanout $GUI_GATER_MAX_FANOUT "
        puts $ckgt_cmd
        eval $ckgt_cmd
        append compile_ultra_hier_opt " -gate_clock "

        set ICG_CELL [get_cells -hier -filter "ref_name=~$GUI_RTL_ICG_TYPE*"]
        set ICG_NUM [sizeof $ICG_CELL]
        if { $ICG_NUM  > 0 } {
        identify_clock_gating -gating_element [get_cells -hier -filter "ref_name=~$GUI_RTL_ICG_TYPE*"]
 }


}

## for low power opt
if { $GUI_POWER_OPT } {
        if { $GUI_DCG_MODE } { set_power_prediction true }
        set_leakage_optimization true
        set_dynamic_optimization true
}

## check design and timing pre compiler
check_design > ../reports/check_design_pre.rpt
check_timing > ../reports/check_timing_pre.rpt

## Prevent assignment statements in the Verilog netlist
set_fix_multiple_port_nets -all -buffer_constants
set_app_var verilogout_no_tri ture
set_host_options -max_cores $GUI_MAX_CPU_NUM
set_cost_priority -delay

## scan
if { $GUI_DFT } {
        append compile_ultra_hier_opt " -scan"
}

##compiler
set compile_ultra_cmd "compile_ultra -no_seq_output_inversion $compile_ultra_hier_opt"
if { $GUI_DCG_MODE } { append compile_ultra_cmd " -spg" }
echo $compile_ultra_cmd
eval $compile_ultra_cmd

## define bus name style
define_name_rules verilog -target_bus_naming_style {%s[%d]} -case_insensitive
change_name -rules verilog -hierarchy

## Report timing cell power area and constraint
set report_timing_opt   "-transition_time -input_pins -capacitance -nets -significant_digits 3 -sort_by slack"
if { $GUI_REPORT_VIOLATION } { append report_timing_opt " -slack_lesser_than 0" }
foreach_in_collection each_path_group [get_path_group] {
        set path_group [get_object_name $each_path_group]
        regsub -all / $path_group _ path_group_rp
        eval report_timing -max_paths 1000 $report_timing_opt -group $path_group > ../reports/${path_group_rp}_max.tim
}
report_constraint -all_violators -significant_digits 3 > ../reports/violation.rpt
report_qor -significant_digits 3 > ../reports/qor.rpt
report_cell > ../reports/cell.rpt
report_power -hierarchy -verbose > ../reports/power.rpt
report_power -hierarchy -levels 2 -verbose  > ../reports/power_level2.rpt
report_clock_gating > ../reports/clock_gating.rpt
check_design > ../reports/check_design.rpt
check_timing > ../reports/check_timing.rpt
report_hierarchy -noleaf > ../reports/hierarchy.rpt

if { $GUI_DCG_MODE } { set report_area_phy_opt "-physical" }
eval report_area $report_area_phy_opt $hierarchy_opt > ../reports/area.rpt

foreach key [array names STD_LIBRARY_NAME] {
    set lib_type [lindex [split $key ,] 0]
    set lib_pvt  [lindex [split $key ,] 1]
    if { [regexp " $lib_type " " $GUI_STD_LIBRARY "] && $lib_pvt == $GUI_PVT } {
        set_attribute [get_libs $STD_LIBRARY_NAME($key)] -type string default_threshold_voltage_group $lib_type
        echo "set_attribute [get_libs $STD_LIBRARY_NAME($key)] -type string default_threshold_voltage_group $lib_type"
    }
}

report_threshold_voltage_group > ../reports/MultiVt.rpt

### dataout
if {$GUI_SYN_CYCLE == 1} {
   rename_design -postfix _${GUI_DESIGN_NAME} -update_links [remove_from_collection [get_designs] ${GUI_DESIGN_NAME}]
   create_block_abstraction
   eval write -format ddc -output ../outputs/${GUI_DESIGN_NAME}_dc.ddc $hierarchy_opt
   eval write -format verilog -output ../outputs/${GUI_DESIGN_NAME}_dc.v $hierarchy_opt
   write_sdc -version 1.8 ../outputs/${GUI_DESIGN_NAME}_dc.sdc
   if { $GUI_UNGROUP_FILE != "" } {
       foreach {cell instance} [get_instance_name $GUI_UNGROUP_FILE] {
           current_design $GUI_DESIGN_NAME
           characterize   $instance
           current_design $cell
           write_sdc -version 1.8 ../outputs/${cell}_dc.sdc
       }
   }
   
   if { $GUI_DCG_MODE } {
       eval write_def -all_vias -output ../outputs/${GUI_DESIGN_NAME}_dc.def
       uniquify
       write_milkyway -output ${GUI_DESIGN_NAME}_dc -overwrite
   }
}
## for compile iterative
if { $GUI_SYN_CYCLE != 1 } {
    for {set i 2} {$i <= $GUI_SYN_CYCLE} {incr i} {
        set compile_ultra_cmd "compile_ultra -no_seq_output_inversion $compile_ultra_hier_opt -incremental"
        if { $GUI_DCG_MODE } { append compile_ultra_cmd " -spg" }
        echo $compile_ultra_cmd
        eval $compile_ultra_cmd
        if {$i == $GUI_SYN_CYCLE} { 
            create_block_abstraction
            eval write -format ddc -output ../outputs/${GUI_DESIGN_NAME}_dc_loop_$i.ddc $hierarchy_opt
            eval write -format verilog -output ../outputs/${GUI_DESIGN_NAME}_dc_loop_$i.v $hierarchy_opt
            write_sdc ../outputs/${GUI_DESIGN_NAME}_dc_loop_$i.sdc

            if { $GUI_DCG_MODE } {
                eval write_def -all_vias -output ../outputs/${GUI_DESIGN_NAME}_dc_loop_$i.def
                uniquify
                write_milkyway -overwrite -output ${GUI_DESIGN_NAME}_loop_$i
            }

            report_constraint -all_violators -significant_digits 3 > ../reports/violation_loop_$i.rpt
            report_qor -significant_digits 3 > ../reports/qor_$APP_loop_$i.rpt
            report_cell > ../reports/cell_loop_$i.rpt
            report_power -hierarchy -verbose > ../reports/power_$APP_loop_$i.rpt
            report_power -hierarchy -levels 2 -verbose  > ../reports/power_$APP_level2_loop_$i.rpt
            report_clock_gating > ../reports/clock_gating_loop_$i.rpt
            check_design > ../reports/check_design_loop_$i.rpt
            check_timing > ../reports/check_timing_loop_$i.rpt
            report_hierarchy -noleaf > ../reports/hierarchy_loop_$i.rpt
            eval report_area $report_area_phy_opt $hierarchy_opt > ../reports/area_loop_$i.rpt
            report_timing \
                -sort_by group -max_paths 100000 -capacitance \
                -trans -significant_digits 3 -nets > ../reports/timing_loop_$i.rpt
            report_qor > ../reports/QoR_loop_$i.rpt
        }
    }
}

set_svf -off
print_message_info
set endtime [clock seconds]
report_runtime
if { !$GUI_DEBUG_MODE } { exit }
