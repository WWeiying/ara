# Exercise the actual integrated report commands on a small mapped design.
# Run inside the EDA container, with REPO_ROOT and a disposable current dir.
set root $env(REPO_ROOT)
source $root/backend/syn/ara_soc/v1-dc/global_scripts/dc_flow_state.tcl
source $root/backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env
set_app_var target_library $STD_LIBRARY_LIST(BWP12T,tc)
set_app_var link_library "* $target_library dw_foundation.sldb"
set_app_var synthetic_library dw_foundation.sldb
set_host_options -max_cores 2
define_design_lib WORK -path ./work
if {![analyze -format sverilog $root/verification/timing/dc_reports_smoke.sv]} {exit 1}
if {![elaborate dc_reports_smoke]} {exit 1}
if {![link]} {exit 1}
create_clock -name clk_i -period 1.0 [get_ports clk_i]
set_clock_uncertainty -setup 0.15 [get_clocks clk_i]
set_input_delay -max 0.5 -clock clk_i [get_ports {enable_i data_i*}]
set_output_delay -max 0.4 -clock clk_i [all_outputs]
group_path -name INPUTS -from [get_ports {enable_i data_i*}]
group_path -name OUTPUTS -to [all_outputs]
if {![compile]} {exit 1}
file mkdir ../reports
redirect ../reports/area.rpt {report_area -hierarchy}
set report_timing_opt {-input_pins -nets -significant_digits 3 -sort_by slack}
set f [open $root/backend/syn/ara_soc/v1-dc/global_scripts/dc.tcl r]
set flow [read $f]
close $f
set first [string first {set akv_macro_ref } $flow]
set marker {close $physical_summary}
set last [string first $marker $flow $first]
if {$first < 0 || $last < 0} {error "Physical report block not found"}
eval [string range $flow $first [expr {$last + [string length $marker] - 1}]]
if {$design_total_area <= 0 || ![string is double -strict $worst_setup_slack] ||
    ![string is double -strict $worst_reg_slack]} {
    error "Physical summary contains missing or nonscalar metrics"
}
puts "DC_REPORTS_SMOKE_PASS area=$design_total_area setup=$worst_setup_slack reg=$worst_reg_slack"
print_message_info
if {![dc_flow_check_errors]} {exit 1}
exit
