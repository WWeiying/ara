# Source after reading/linking a mapped ordered_add_ppa_top checkpoint.
# Report-only: never compile or alter the mapped netlist in this session.
# Operation encoding is from the pinned fpnew_pkg: ADD=2.
# Sequential propagation is necessary for the BEFORE operation/format registers.
# Inspect each propagation log to confirm that propagation reaches them;
# report_case_analysis itself lists constraints, not propagated values.
set_app_var case_analysis_sequential_propagation always
set_case_analysis 1 [get_ports rst_ni]
foreach_in_collection port [get_ports -quiet {op_i[*]}] {
  set name [get_object_name $port]
  if {![regexp {\[([0-9]+)\]$} $name -> bit]} {
    error "Unexpected operation port: $name"
  }
  set_case_analysis [expr {(2 >> $bit) & 1}] $port
}
set_case_analysis 0 [get_ports op_mod_i]
# Enabled input flops have a feedback mux. Port case analysis alone did not
# constrain their Q pins in the original mapped design. Every valid request
# on this dedicated instance is ADD with op_mod=0, in every format.
set op_register_count 0
foreach_in_collection cell [get_cells -hierarchical -filter {is_sequential == true}] {
  set name [get_object_name $cell]
  if {[regexp {inp_pipe_op_q_reg\[1\]\[([0-9]+)\]$} $name -> bit]} {
    set value [expr {(2 >> $bit) & 1}]
  } elseif {[regexp {inp_pipe_op_mod_q_reg\[1\]$} $name]} {
    set value 0
  } else {
    continue
  }
  set pins [get_pins -of_objects $cell -filter {direction == out}]
  if {[sizeof_collection $pins] == 0} {error "No output on $name"}
  foreach_in_collection pin $pins {
    set pin_name [get_object_name $pin]
    if {[regexp {/Q$} $pin_name]} {
      set_case_analysis $value $pin
    } elseif {[regexp {/QN$} $pin_name]} {
      set_case_analysis [expr {1-$value}] $pin
    } else {
      error "Unverified register output polarity: $pin_name"
    }
  }
  incr op_register_count
}
# Original SIMD instance has 2 FP32 + 1 FP64 + 4 FP16 slices, each with
# five operation bits and one operation-modifier bit. Fail on netlist drift.
if {[string match *_Mode0 [get_object_name [current_design]]] && $op_register_count != 42} {
  error "Expected 42 original operation registers, found $op_register_count"
}
puts "ORDERED_ADD_CONSTRAINED_REGISTERS $op_register_count"
# Leave formats, mask, rounding, valid/ready and operands unconstrained.
# This reports the worst ADD path across all supported formats, not a fixed
# stream or a proof of full-SoC timing closure. Preserve unrestricted reports.
set_app_var case_analysis_log_file add_case_propagation.log
report_timing -max_paths 10 -significant_digits 6 > add_timing.rpt
report_case_analysis -all > add_case_analysis.rpt
check_timing > add_check_timing.rpt
puts ORDERED_ADD_MODE_TIMING_COMPLETE
