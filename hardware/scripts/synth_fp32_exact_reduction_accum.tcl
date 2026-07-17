# Standalone PPA ablation for fp32_exact_reduction_accum.
#
# Usage:
#   SEGMENTED=0 REPORT_DIR=/tmp/exact_flat dc_shell -f this_file
#   SEGMENTED=1 REPORT_DIR=/tmp/exact_segmented dc_shell -f this_file

set segmented 0
if {[info exists env(SEGMENTED)]} {
  set segmented $env(SEGMENTED)
}

set report_dir "/tmp/fp32_exact_reduction_accum_${segmented}"
if {[info exists env(REPORT_DIR)]} {
  set report_dir $env(REPORT_DIR)
}
file mkdir $report_dir

set script_dir [file dirname [file normalize [info script]]]
set rtl_file [file normalize \
  [file join $script_dir ../src/lane/fp32_exact_reduction_accum.sv]]

set stdcell_db \
  /home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_180a_nldm/TSMCHOME/digital/Front_End/timing_power_noise/NLDM/tcbn28hpcplusbwp12t40p140_180a/tcbn28hpcplusbwp12t40p140tt0p9v25c.db
set synthetic_db \
  /home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2/libraries/syn/dw_foundation.sldb

set_app_var target_library [list $stdcell_db]
set_app_var synthetic_library [list $synthetic_db]
set_app_var link_library [concat "*" $target_library $synthetic_library]
set_app_var search_path [concat [file dirname $rtl_file] $search_path]

define_design_lib WORK -path [file join $report_dir work]
analyze -format sverilog -define SYNTHESIS $rtl_file
elaborate fp32_exact_reduction_accum \
  -parameters "AccWidth=288,ExponentSegmented=$segmented"
current_design fp32_exact_reduction_accum
link

create_clock -name clk -period 2.0 [get_ports clk_i]
set_clock_uncertainty 0.10 [get_clocks clk]
set_input_delay 0.10 -clock clk \
  [remove_from_collection [all_inputs] [get_ports clk_i]]
set_output_delay 0.10 -clock clk [all_outputs]
set_driving_cell -lib_cell BUFFD4BWP12T40P140 \
  [remove_from_collection [all_inputs] [get_ports clk_i]]
set_load 0.02 [all_outputs]
set_max_area 0

check_design > [file join $report_dir check_design.rpt]
compile_ultra -no_autoungroup

report_qor > [file join $report_dir qor.rpt]
report_area -hierarchy > [file join $report_dir area.rpt]
report_timing -delay_type max -max_paths 20 -nworst 5 \
  > [file join $report_dir timing.rpt]
report_power -analysis_effort medium > [file join $report_dir power.rpt]
write -format ddc -hierarchy -output \
  [file join $report_dir fp32_exact_reduction_accum.ddc]

quit
