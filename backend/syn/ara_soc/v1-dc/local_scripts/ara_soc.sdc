###################################################################################
## parameter define ,modify by custom
###################################################################################
set clk_mul 1.25
set uncertainty_add 0.2

set clk_driving_cell {CKBD4BWP12T40P140 I Z}
set data_driving_cell {BUFFD4BWP12T40P140 I Z}
set output_load 0.02
set max_fanout 32
set max_transition 0.4
#30%~50%
set input_delay [expr {0.5 * $clk_mul}]
#25%~40%
set output_delay [expr {0.4 * $clk_mul}]

###################################################################################
## common timing constrains
###################################################################################
#clock define
create_clock -name clk_i -period [expr {1 * $clk_mul}]  [get_ports clk_i]
#10%~20%
set_clock_uncertainty -setup [expr {(0.15 + $uncertainty_add) * $clk_mul}] [get_clocks clk_i]
# 5%~10%
set_clock_uncertainty -hold  0.075 [get_clocks clk_i]
# 3%~8%
set_clock_transition 0.08 clk_i
#
set_ideal_network [get_ports {clk_i rst_ni}]                                                                                                                                              

#set all_real_clock [filter_collection [get_attribute [get_clocks] sources] object_class==port]
#if {$synopsys_program_name == "dc_shell" || $synopsys_program_name == "icc_shell" } { set_ideal_network $all_real_clock }
#if {$synopsys_program_name == "pt_shell"} { set_propagated_clock [all_clocks]}
###common constrains
set_max_fanout $max_fanout [current_design]
set_max_transition $max_transition [current_design]
###inputs driving
remove_ideal_network [get_ports clk_i]

set_driving_cell -lib_cell [lindex $clk_driving_cell 0] -pin [lindex $clk_driving_cell 2] -from_pin [lindex $clk_driving_cell 1] \
                 -input_transition_rise 0.15 -input_transition_fall 0.15 \
                 [get_ports clk_i]
set_driving_cell -lib_cell [lindex $data_driving_cell 0] -pin [lindex $data_driving_cell 2] -from_pin [lindex $data_driving_cell 1] \
                 -input_transition_rise 0.3 -input_transition_fall 0.3 \
                 [remove_from_collection [all_inputs] [get_ports clk_i]]
###outputs load
set_load $output_load [all_outputs]
###group path
group_path -name INPUTS -from [remove_from_collection [all_inputs] [get_ports clk_i]]
group_path -name OUTPUTS -to [all_outputs]
group_path -name COMBO -from [remove_from_collection [all_inputs] [get_ports clk_i]] -to [all_outputs]
group_path -name clk_i -critical 0.2 -weight 5
###################################################################################
###port timing constrains & special constrains
###################################################################################
set_input_delay -clock clk_i -max $input_delay [remove_from_collection [all_inputs] [get_ports clk_i]]
set_output_delay -clock clk_i -max $output_delay [all_outputs]

set_false_path -from [get_ports rst_ni] -to [all_registers]
set_false_path -to [get_pins i_system/i_ariane/rvfi_probes_o]
