# Matched local subsystem comparison; not whole-SoC signoff or power evidence.
source library_env.tcl
set_app_var target_library $STD_LIBRARY_LIST(BWP12T,tc)
set_app_var synthetic_library dw_foundation.sldb
set_app_var link_library "* $target_library $synthetic_library"
set_app_var search_path [concat ./src $search_path]
set_host_options -max_cores 2
define_design_lib WORK -path ./work
set hdlin_check_no_latch true
set compile_enable_register_merging false
set compile_seqmap_propagate_constants false
set sources {src/cf_math_pkg.sv src/axi_pkg.sv src/fpnew_pkg.sv
 src/config_pkg.sv src/cv64a6_imafdcv_sv39_config_pkg.sv src/riscv_pkg.sv
 src/rvv_pkg.sv src/ara_pkg.sv src/fixed_p_rounding.sv src/simd_alu.sv
 src/simd_alu_timing.sv}
set defines {SYNTHESIS}
if {![analyze -format sverilog -define $defines $sources]} {exit 1}
if {![elaborate simd_alu_timing]} {exit 1}
if {![link]} {exit 1}
create_clock -name clk_i -period 1.0 [get_ports clk_i]
set_clock_uncertainty -setup 0.15 [get_clocks clk_i]
set_clock_uncertainty -hold 0.075 [get_clocks clk_i]
set_clock_transition 0.08 [get_clocks clk_i]
set inputs [remove_from_collection [all_inputs] [get_ports {clk_i rst_ni}]]
set_input_delay -clock clk_i -max 0.5 $inputs
set_output_delay -clock clk_i -max 0.4 [all_outputs]
set_driving_cell -lib_cell BUFFD4BWP12T40P140 -pin Z $inputs
set_load 0.02 [all_outputs]
set_max_fanout 32 [current_design]
set_max_transition 0.4 [current_design]
set_false_path -from [get_ports rst_ni]
group_path -name INPUTS -from $inputs
group_path -name OUTPUTS -to [all_outputs]
group_path -name COMBO -from $inputs -to [all_outputs]
group_path -name clk_i -critical 0.2 -weight 5
set_fix_multiple_port_nets -all -buffer_constants
redirect check_pre.rpt {check_design}
redirect resources.rpt {report_resources -hierarchy}
write -format ddc -hierarchy -output elaborated.ddc
set_clock_gating_style -sequential latch \
 -positive_edge_logic {integrated:CKLNQD4BWP12T40P140} \
 -control_point before -minimum_bitwidth 4 -setup 0.2 -num_stages 1 -max_fanout 32
if {![compile_ultra -no_autoungroup -no_seq_output_inversion -gate_clock]} {exit 1}
write -format ddc -hierarchy -output mapped.ddc
redirect area.rpt {report_area -hierarchy}
redirect qor.rpt {report_qor}
redirect clk_i_max.tim {report_timing -group clk_i -delay_type max -max_paths 20 -input_pins -nets -transition_time -capacitance -significant_digits 4}
redirect check_post.rpt {check_design}
redirect check_timing.rpt {check_timing}
redirect references.rpt {report_reference -hierarchy}
set area_file [open area.rpt r]
set area_text [read $area_file]
close $area_file
if {![regexp {Total cell area:\s+([0-9]+\.[0-9]+)} $area_text unused cell_area]} {
  error "Missing total cell area in mapped area report"
}
if {$cell_area <= 0} {error "Invalid mapped cell area"}
set f [open metrics.tsv w]
puts $f "area_um2\t$cell_area"
set paths [get_timing_paths -group clk_i -delay_type max -max_paths 1]
if {[sizeof_collection $paths] != 1} {error "No register-group timing path"}
puts $f "clk_i_slack_ns\t[get_attribute $paths slack]"
puts $f "clk_i_arrival_ns\t[get_attribute $paths arrival]"
close $f
puts "SHARED_ALU_PPA_COMPLETE"
exit
