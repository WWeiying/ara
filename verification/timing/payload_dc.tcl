# Local path diagnosis, not a replacement for constrained ara_soc signoff.
set out [pwd]
set local_starttime [clock seconds]
source ./library_env.tcl
set_app_var target_library $STD_LIBRARY_LIST(BWP12T,tc)
set_app_var synthetic_library dw_foundation.sldb
set_app_var link_library "* $target_library $ts1n28hpcpuhdsvtb8x128m1swbso_170a $ts1n28hpcpuhdsvtb8x256m1swbso_170a $synthetic_library"
set_host_options -max_cores 2
define_design_lib WORK -path ./work
set hdlin_check_no_latch true
set compile_enable_register_merging false
set compile_seqmap_propagate_constants false
set top qbs_payload_buffer
if {[info exists env(DC_LOCAL_TOP)]} {set top $env(DC_LOCAL_TOP)}
if {$top ni {qbs_payload_buffer qbs_block_adapter qbs_ingress_timing qbs_adapter_pipeline_timing simd_mul_timing
             simd_alu_timing qbs_decode_dot_timing vfdsu_round_timing ara_dispatcher_timing
             qbs_correction_select_timing qbs_address_timing qbs_profile_pipeline_timing}} {
  error "unsupported local top: $top"
}
set sources {
  src/qbs_pkg.sv src/qbs_payload_sram.sv src/qbs_payload_buffer.sv
}
if {$top in {qbs_block_adapter qbs_ingress_timing qbs_adapter_pipeline_timing}} {lappend sources src/qbs_block_adapter.sv}
if {$top eq "qbs_ingress_timing"} {lappend sources src/qbs_ingress_timing.sv}
if {$top eq "qbs_adapter_pipeline_timing"} {lappend sources src/qbs_adapter_pipeline_timing.sv}
if {$top eq "qbs_decode_dot_timing"} {
  set sources {src/qbs_pkg.sv src/qbs_profile_decoder.sv src/qbs_dot_array.sv
    src/qbs_decode_dot_timing.sv}
}
if {$top eq "qbs_profile_pipeline_timing"} {
  set sources {src/cf_math_pkg.sv src/lzc.sv src/qbs_pkg.sv
    src/qbs_profile_decoder.sv src/qbs_dot_array.sv src/qbs_profile_engine_int.sv
    src/qbs_profile_pipeline_timing.sv}
  set_app_var search_path [concat ./src $search_path]
}
if {$top eq "vfdsu_round_timing"} {
  set sources {src/gated_clk_cell.v src/ct_vfdsu_round.v src/vfdsu_round_timing.sv}
}
set defines {SYNTHESIS TARGET_SRAM_MC}
if {[info exists env(DC_UNIQUE_INPUT_BYTES)] && $env(DC_UNIQUE_INPUT_BYTES) == 1} {
  lappend defines QBS_UNIQUE_INPUT_BYTES
}
if {$top in {simd_mul_timing simd_alu_timing ara_dispatcher_timing}} {
  set sources {src/cf_math_pkg.sv src/axi_pkg.sv src/fpnew_pkg.sv
    src/config_pkg.sv src/cv64a6_imafdcv_sv39_config_pkg.sv src/riscv_pkg.sv
    src/rvv_pkg.sv src/ara_pkg.sv}
  if {$top eq "simd_mul_timing"} {
    lappend sources src/simd_mul.sv src/simd_mul_timing.sv
  } elseif {$top eq "simd_alu_timing"} {
    lappend sources src/simd_alu.sv src/fixed_p_rounding.sv src/simd_alu_timing.sv
  } else {
    lappend sources src/build_config_pkg.sv src/qbs_pkg.sv src/akv_pkg.sv \
      src/dispatcher_check_pkg.sv src/popcount.sv src/delta_counter.sv src/counter.sv \
      src/segment_sequencer.sv src/ara_dispatcher.sv src/ara_dispatcher_timing.sv
    lappend defines ARA_QBS_ENABLE ARA_AKV_ENABLE ARA_AKV_V2_ENABLE
  }
  set_app_var search_path [concat ./src $search_path]
}
if {$top in {qbs_correction_select_timing qbs_address_timing}} {
  set sources [list src/cf_math_pkg.sv src/lzc.sv src/${top}.sv]
  set_app_var search_path [concat ./src $search_path]
}
if {![analyze -format sverilog -define $defines $sources]} {exit 1}
if {$top eq "simd_mul_timing"} {
  set ew $env(DC_ELEMENT_WIDTH)
  if {$ew ni {0 1 2 3}} {error "invalid multiplier SEW"}
  set pipes [expr {$ew == 0 ? 0 : 1}]
  if {![elaborate $top -parameters "ElementWidth=$ew,NumPipeRegs=$pipes"]} {exit 1}
} elseif {$top ni {qbs_ingress_timing qbs_adapter_pipeline_timing} && [info exists env(DC_COMPACT_READ)] && $env(DC_COMPACT_READ) == 1} {
  if {![elaborate $top -parameters "NativeView=0"]} {exit 1}
} else {
  if {![elaborate $top]} {exit 1}
}
# Elaborate selects the parameterized top (for example *_NativeView0).
# Selecting the unparameterized module name can fail even after successful RTL elaboration.
puts "ELABORATED_TOP=[get_object_name [current_design]]"
if {![link]} {error "payload link failed"}
create_clock -name clk_i -period 1.0 [get_ports clk_i]
set_clock_uncertainty -setup 0.15 [get_clocks clk_i]
set_clock_uncertainty -hold 0.075 [get_clocks clk_i]
set_clock_transition 0.08 [get_clocks clk_i]
set data_inputs [remove_from_collection [all_inputs] [get_ports {clk_i rst_ni}]]
set_input_delay -clock clk_i -max 0.5 $data_inputs
set_output_delay -clock clk_i -max 0.4 [all_outputs]
set_driving_cell -lib_cell BUFFD4BWP12T40P140 -pin Z $data_inputs
set_load 0.02 [all_outputs]
set_max_fanout 32 [current_design]
set_max_transition 0.4 [current_design]
set_false_path -from [get_ports rst_ni]
group_path -name INPUTS -from $data_inputs
group_path -name OUTPUTS -to [all_outputs]
group_path -name COMBO -from $data_inputs -to [all_outputs]
group_path -name clk_i -critical 0.2 -weight 5
set_fix_multiple_port_nets -all -buffer_constants
redirect check_pre.rpt {check_design}
write -format ddc -hierarchy -output elaborated.ddc
redirect elaborated_references.rpt {report_reference -hierarchy}
redirect elaborated_resources.rpt {report_resources -hierarchy}
puts "LOCAL_TOP=$top"
if {[llength [info commands report_runtime]]} {
  report_runtime
} else {
  puts "LOCAL_DC_ELAPSED_SECONDS=[expr {[clock seconds] - $local_starttime}]"
}
if {[info exists env(DC_ELAB_ONLY)] && $env(DC_ELAB_ONLY) == 1} {
  puts "PAYLOAD_DC_ELAB_COMPLETE"
  exit
}
if {$top in {qbs_ingress_timing qbs_adapter_pipeline_timing simd_mul_timing simd_alu_timing qbs_decode_dot_timing vfdsu_round_timing ara_dispatcher_timing qbs_correction_select_timing qbs_address_timing qbs_profile_pipeline_timing}} {
  # Match the integrated run's clock gate and setup requirement exactly.
  set_clock_gating_style -sequential latch \
      -positive_edge_logic {integrated:CKLNQD4BWP12T40P140} \
      -control_point before -minimum_bitwidth 4 -setup 0.2 \
      -num_stages 1 -max_fanout 32
  if {![compile_ultra -no_autoungroup -no_seq_output_inversion -gate_clock]} {exit 1}
} else {
  if {![compile_ultra -no_autoungroup -no_seq_output_inversion]} {exit 1}
}
# Save the mapped database before potentially expensive reporting.
write -format ddc -hierarchy -output mapped.ddc
redirect qor.rpt {report_qor}
redirect area.rpt {report_area -hierarchy}
redirect timing.rpt {
  report_timing -delay_type max -max_paths 20 -input_pins -nets \
      -transition_time -capacitance -significant_digits 4
}
set quick_reports [expr {[info exists env(DC_LOCAL_QUICK_REPORTS)] && $env(DC_LOCAL_QUICK_REPORTS) == 1}]
if {!$quick_reports} {
  redirect reg_to_reg.rpt {
    report_timing -delay_type max -from [all_registers -edge_triggered -output_pins] \
        -to [all_registers -edge_triggered -data_pins] -max_paths 20 -input_pins -nets \
        -transition_time -capacitance -significant_digits 4
  }
}
set clock_report_paths [expr {$quick_reports ? 20 : 1000}]
redirect clk_i_max.tim {
  report_timing -group clk_i -delay_type max -max_paths $clock_report_paths -input_pins -nets \
      -transition_time -capacitance -significant_digits 4
}
if {$top in {qbs_ingress_timing qbs_adapter_pipeline_timing simd_mul_timing simd_alu_timing qbs_decode_dot_timing vfdsu_round_timing ara_dispatcher_timing qbs_correction_select_timing qbs_address_timing qbs_profile_pipeline_timing}} {
  redirect clock_gating.rpt {report_clock_gating}
}
if {$top eq "ara_dispatcher_timing"} {
  redirect ready_to_response.rpt {
    report_timing -from [get_ports ara_req_ready_i] -to [get_ports response_valid_o] \
      -delay_type max -max_paths 4 -input_pins -nets -transition_time -capacitance \
      -significant_digits 4
  }
  redirect completion_to_response.rpt {
    report_timing -from [get_ports ara_resp_valid_i] -to [get_ports response_valid_o] \
      -delay_type max -max_paths 4 -input_pins -nets -transition_time -capacitance \
      -significant_digits 4
  }
}
redirect check_timing.rpt {check_timing}
redirect references.rpt {report_reference -hierarchy}
puts "PAYLOAD_DC_COMPLETE"
exit
