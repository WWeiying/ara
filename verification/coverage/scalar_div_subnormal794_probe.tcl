# Read-only aggregate parents plus the source-bound DIV exponent/rounding chain.
set sd ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.fpu_gen.fpu_i
set ds ${sd}.fpu_gen.i_fpnew_bulk.gen_operation_groups\[1\].i_opgroup_block.gen_merged_slice.i_multifmt_slice.gen_num_lanes\[0\].active_lane.lane_instance.gen_thmulti_c910_divsqrt.i_fpnew_divsqrt_th_64_c910.i_ct_vfdsu_top.x_ct_vfdsu_double
set paths [list ara_tb.clk ara_tb.rst_n ${sd}.flush_i ${sd}.state_q \
    ${sd}.fpu_valid_i ${sd}.fpu_ready_o ${sd}.fu_data_i ${sd}.fpu_valid_o \
    ${sd}.fpu_trans_id_o ${sd}.result_o ${sd}.fpu_exception_o \
    ${sd}.fpu_gen.fpu_tag_d ${sd}.fpu_gen.fpu_op_d ${sd}.fpu_gen.fpu_rm_d ${sd}.fpu_gen.fpu_in_ready \
    ${sd}.fpu_gen.fpu_in_valid ${sd}.fpu_gen.hold_inputs ${sd}.fpu_gen.use_hold \
    ${sd}.fpu_gen.operand_a_d ${sd}.fpu_gen.operand_b_d ${sd}.fpu_gen.operand_c_d \
    ${sd}.fpu_gen.operand_a_q ${sd}.fpu_gen.operand_b_q ${sd}.fpu_gen.operand_c_q \
    ${sd}.fpu_gen.fpu_op_q ${sd}.fpu_gen.fpu_rm_q ${sd}.fpu_gen.fpu_tag_q \
    ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands.issue_instr_i \
    ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands.fpu_valid_n \
    ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands.fu_data_n \
    ${ds}.x_ct_vfdsu_srt.ex2_pipedown ${ds}.x_ct_vfdsu_srt.vfdsu_ex2_double \
    ${ds}.x_ct_vfdsu_srt.vfdsu_ex2_sqrt ${ds}.x_ct_vfdsu_srt.vfdsu_ex2_expnt_rst \
    ${ds}.x_ct_vfdsu_srt.ex2_result_double_denorm_round_add_num \
    ${ds}.x_ct_vfdsu_srt.ex2_result_denorm_round_add_num \
    ${ds}.x_ct_vfdsu_srt.vfdsu_ex3_result_denorm_round_add_num \
    ${ds}.x_ct_vfdsu_round.ex3_pipedown ${ds}.x_ct_vfdsu_round.ex3_rslt_denorm \
    ${ds}.x_ct_vfdsu_round.vfdsu_ex3_result_denorm_round_add_num \
    ${ds}.x_ct_vfdsu_round.frac_add1_op1_with_denorm \
    ${ds}.x_ct_vfdsu_round.frac_sub1_op1_with_denorm]
if {[catch {
    set fid [dump -file scalar-div-subnormal794.vpd -type VPD]
    foreach path $paths {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
    }
    puts SUBNORMAL_DIV_PROBE_READY
    run
} failure]} {
    puts "SUBNORMAL_DIV_PROBE_ERROR $failure"
    exit 1
}
