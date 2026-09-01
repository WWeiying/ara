# Standalone 1 GHz synthesis for the complete QBS+AKV-v2 engine boundary.
if {[info exists ::env(ARA_ROOT)]} {
  set ara_root [file normalize $::env(ARA_ROOT)]
} else {
  set ara_root [file normalize [file join [file dirname [info script]] ../../..]]
}

set output_dir [file normalize [file join [pwd] akv_engine_dc_out]]
set dc_filelist [file join $ara_root backend/flist/ara_soc_dc.f]
set wrapper [file join $ara_root verification/akv/synthesis/akv_engine_synth_wrapper.sv]
set project_sdc [file join $ara_root verification/akv/synthesis/akv_engine.sdc]
file mkdir $output_dir
define_design_lib WORK -path [file join $output_dir work]

set std_library "/home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_180a_nldm/TSMCHOME/digital/Front_End/timing_power_noise/NLDM/tcbn28hpcplusbwp12t40p140_180a/tcbn28hpcplusbwp12t40p140tt0p9v25c.db"
set context_sram_library "/home/wangwy/ara/backend/library/mem/ts1n28hpcpuhdsvtb64x256m1swbso_170a/DB/ts1n28hpcpuhdsvtb64x256m1swbso_170a_tt0p9v25c.db"
set synthetic_library "/home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2/libraries/syn/dw_foundation.sldb"

foreach required_file [list $dc_filelist $wrapper $project_sdc $std_library \
                            $context_sram_library $synthetic_library] {
  if {![file isfile $required_file]} {
    error "missing standalone synthesis input: $required_file"
  }
}

set_app_var target_library $std_library
set_app_var synthetic_library $synthetic_library
set_app_var link_library "* $std_library $context_sram_library $synthetic_library"
set_host_options -max_cores 8
set hdlin_check_no_latch true
set compile_seqmap_propagate_constants false
set compile_enable_register_merging false
set compile_register_replication true

analyze -format sverilog -vcs "-f $dc_filelist"
analyze -format sverilog $wrapper
elaborate akv_engine_synth_wrapper
current_design akv_engine_synth_wrapper
link

redirect [file join $output_dir check_design_pre.rpt] {check_design}
source -echo -verbose $project_sdc
set_register_merging [current_design] false
set_fix_multiple_port_nets -all -buffer_constants
set_app_var verilogout_no_tri true
set_cost_priority -delay

compile_ultra -no_autoungroup -no_seq_output_inversion

redirect [file join $output_dir check_design.rpt] {check_design}
redirect [file join $output_dir check_timing.rpt] {check_timing}
redirect [file join $output_dir area.rpt] {report_area -hierarchy}
redirect [file join $output_dir timing.rpt] {
  report_timing -delay_type max -max_paths 50 -transition_time -capacitance
}
redirect [file join $output_dir timing_reg_to_reg.rpt] {
  report_timing -delay_type max -from [all_registers] -to [all_registers] \
      -max_paths 50 -transition_time -capacitance
}
redirect [file join $output_dir qor.rpt] {report_qor}
redirect [file join $output_dir references.rpt] {report_reference -hierarchy}
redirect [file join $output_dir resources.rpt] {report_resources}

set macro_ref TS1N28HPCPUHDSVTB64X256M1SWBSO
set context_macros [get_cells -hierarchical -filter "ref_name == $macro_ref"]
set v1_macros [get_cells -hierarchical -filter \
    "ref_name == $macro_ref && full_name =~ i_akv_engine/i_context/*"]
set v2_macros [get_cells -hierarchical -filter \
    "ref_name == $macro_ref && full_name =~ i_akv_engine/i_v2_context/*"]
set macro_count [sizeof_collection $context_macros]
set v1_macro_count [sizeof_collection $v1_macros]
set v2_macro_count [sizeof_collection $v2_macros]
if {$macro_count != 20 || $v1_macro_count != 4 || $v2_macro_count != 16} {
  error "unexpected AKV SRAM organization: total=$macro_count v1=$v1_macro_count v2=$v2_macro_count"
}

set macro_area 0.0
foreach_in_collection macro $context_macros {
  set macro_area [expr {$macro_area + [get_attribute $macro area]}]
}
set total_area [get_attribute [current_design] area]
set logic_area [expr {$total_area - $macro_area}]
set worst_path [get_timing_paths -delay_type max -max_paths 1]
set reg_path [get_timing_paths -delay_type max -from [all_registers] \
    -to [all_registers] -max_paths 1]
set worst_slack [get_attribute $worst_path slack]
set reg_slack [get_attribute $reg_path slack]

set report_file [open [file join $output_dir engine_summary.rpt] w]
puts $report_file "clock_period_ns=1.0"
puts $report_file "clock_uncertainty_ns=0.15"
puts $report_file "physical_sram_macro_count=$macro_count"
puts $report_file "v1_sram_macro_count=$v1_macro_count"
puts $report_file "v2_sram_macro_count=$v2_macro_count"
puts $report_file "physical_sram_capacity_bits=[expr {$macro_count * 64 * 256}]"
puts $report_file "design_total_area_um2=$total_area"
puts $report_file "sram_macro_area_um2=$macro_area"
puts $report_file "logic_area_um2=$logic_area"
puts $report_file "worst_setup_slack_ns=$worst_slack"
puts $report_file "worst_reg_to_reg_setup_slack_ns=$reg_slack"
close $report_file

write -format ddc -hierarchy -output [file join $output_dir akv_engine.ddc]
write -format verilog -hierarchy -output [file join $output_dir akv_engine.v]
write_sdc -version 1.8 [file join $output_dir akv_engine.sdc]
exit
