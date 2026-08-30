# Standalone 1 GHz synthesis check for the AKV resident context.
if {[info exists ::env(ARA_ROOT)]} {
  set ara_root [file normalize $::env(ARA_ROOT)]
} else {
  set ara_root [file normalize [file join [file dirname [info script]] ../../..]]
}

set output_dir [file normalize [file join [pwd] akv_context_dc_out]]
file mkdir $output_dir
define_design_lib WORK -path [file join $output_dir work]

set std_library "/home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_180a_nldm/TSMCHOME/digital/Front_End/timing_power_noise/NLDM/tcbn28hpcplusbwp12t40p140_180a/tcbn28hpcplusbwp12t40p140tt0p9v25c.db"
set context_sram_library "/home/wangwy/ara/backend/library/mem/ts1n28hpcpuhdsvtb64x256m1swbso_170a/DB/ts1n28hpcpuhdsvtb64x256m1swbso_170a_tt0p9v25c.db"
set synthetic_library "/home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2/libraries/syn/dw_foundation.sldb"

set_app_var target_library $std_library
set_app_var synthetic_library $synthetic_library
set_app_var link_library "* $std_library $context_sram_library $synthetic_library"

analyze -format sverilog -define {SYNTHESIS TARGET_SYNTHESIS TARGET_SRAM_MC} [list \
  [file join $ara_root hardware/include/akv_pkg.sv] \
  [file join $ara_root hardware/src/vlsu/akv/akv_context.sv]]
elaborate akv_context
current_design akv_context
link

redirect [file join $output_dir check_design_pre.rpt] {check_design}

create_clock -name clk_i -period 1.0 [get_ports clk_i]
set_clock_uncertainty 0.15 [get_clocks clk_i]
set_false_path -from [get_ports rst_ni]
set data_inputs [remove_from_collection [all_inputs] [get_ports {clk_i rst_ni}]]
set_input_delay 0.10 -clock clk_i $data_inputs
set_output_delay 0.10 -clock clk_i [all_outputs]
set_load 0.02 [all_outputs]

compile_ultra -no_autoungroup

redirect [file join $output_dir check_design.rpt] {check_design}
redirect [file join $output_dir area.rpt] {report_area -hierarchy}
redirect [file join $output_dir timing.rpt] {
  report_timing -delay_type max -max_paths 20 -transition_time -capacitance
}
redirect [file join $output_dir qor.rpt] {report_qor}
redirect [file join $output_dir references.rpt] {report_reference -hierarchy}
redirect [file join $output_dir resources.rpt] {report_resources}

set context_macros [get_cells -hierarchical -filter \
    "ref_name == TS1N28HPCPUHDSVTB64X256M1SWBSO"]
set macro_count [sizeof_collection $context_macros]
set report_file [open [file join $output_dir context_summary.rpt] w]
puts $report_file "clock_period_ns=1.0"
puts $report_file "clock_uncertainty_ns=0.15"
puts $report_file "logical_payload_bits=49152"
puts $report_file "physical_sram_macro_count=$macro_count"
puts $report_file "physical_sram_capacity_bits=[expr {$macro_count * 64 * 256}]"
close $report_file

write -format ddc -hierarchy -output [file join $output_dir akv_context.ddc]
write -format verilog -hierarchy -output [file join $output_dir akv_context.v]
exit
