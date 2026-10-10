# Source-bound read-only FPU owner and initial bound-selector signals.
set fp ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.fpu_gen.fpu_i
set sr ${fp}.fpu_gen.i_fpnew_bulk.gen_operation_groups\[1\].i_opgroup_block.gen_merged_slice.i_multifmt_slice.gen_num_lanes\[0\].active_lane.lane_instance.gen_thmulti_c910_divsqrt.i_fpnew_divsqrt_th_64_c910.i_ct_vfdsu_top.x_ct_vfdsu_double.x_ct_vfdsu_srt
set rd [string range $sr 0 end-[string length x_ct_vfdsu_srt]]x_ct_vfdsu_round
set issue ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands
set paths [list ara_tb.clk ara_tb.rst_n]
foreach n {flush_i state_q fpu_valid_i fpu_ready_o fu_data_i fpu_valid_o fpu_trans_id_o result_o fpu_exception_o} {lappend paths ${fp}.${n}}
foreach n {fpu_tag_d fpu_op_d fpu_rm_d fpu_in_ready fpu_in_valid hold_inputs use_hold operand_a_d operand_b_d operand_c_d operand_a_q operand_b_q operand_c_q fpu_op_q fpu_rm_q fpu_tag_q} {lappend paths ${fp}.fpu_gen.${n}}
foreach n {issue_instr_i fpu_valid_n fu_data_n} {lappend paths ${issue}.${n}}
foreach n {ex2_pipedown vfdsu_ex2_double vfdsu_ex2_sqrt vfdsu_ex2_expnt_rst ex2_result_double_denorm_round_add_num ex2_result_denorm_round_add_num vfdsu_ex3_result_denorm_round_add_num initial_srt_en initial_srt_sel_div_in initial_srt_sel_sqrt_in initial_bound_sel_in} {lappend paths ${sr}.${n}}
foreach n {ex3_pipedown ex3_rslt_denorm vfdsu_ex3_result_denorm_round_add_num frac_add1_op1_with_denorm frac_sub1_op1_with_denorm} {lappend paths ${rd}.${n}}
set iter ${sr}.x_ct_vfdsu_srt_radix16_with_sqrt
lappend paths ${iter}.bound_sel
for {set i 1} {$i<=9} {incr i} {lappend paths ${iter}.x_ct_vfdsu_srt_radix16_bound_table.ori_digit_bound_${i}}
if {[catch {
    set fid [dump -file scalar-c910-pattern795.vpd -type VPD]
    foreach path $paths {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count<=0} {error "Unavailable object $path"}
    }
    puts C910_PATTERN_PROBE_READY
    run
} failure]} {puts "C910_PATTERN_PROBE_ERROR $failure";exit 1}
