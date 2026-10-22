# Read-only observation; no force, deposit, stop, reset or DUT state changes.
set fa ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.fpu_gen.fpu_i
set fg ${fa}.fpu_gen
set ft ${fg}.i_fpnew_bulk
set fa_paths [list ara_tb.clk ara_tb.rst_n ${fa}.flush_i ${fa}.state_q \
    ${fa}.fpu_valid_i ${fa}.fpu_ready_o ${fa}.fu_data_i \
    ${fa}.fpu_trans_id_o ${fa}.result_o ${fa}.fpu_valid_o ${fa}.fpu_exception_o \
    ${fg}.fpu_in_ready ${fg}.fpu_in_valid ${fg}.fpu_out_valid ${fg}.fpu_out_ready \
    ${fg}.hold_inputs ${fg}.use_hold \
    ${fg}.operand_a_d ${fg}.operand_b_d ${fg}.operand_c_d \
    ${fg}.operand_a_q ${fg}.operand_b_q ${fg}.operand_c_q \
    ${fg}.fpu_op_d ${fg}.fpu_op_q ${fg}.fpu_tag_d ${fg}.fpu_tag_q \
    ${ft}.opgrp_in_ready ${ft}.opgrp_out_valid ${ft}.opgrp_out_ready \
    ${ft}.gen_operation_groups\[0\].i_opgroup_block.fmt_in_ready \
    ${ft}.gen_operation_groups\[0\].i_opgroup_block.fmt_out_valid \
    ${ft}.gen_operation_groups\[0\].i_opgroup_block.fmt_out_ready]
if {[catch {
    set fid [dump -file scalar-fpu-fma-arbiter792.vpd -type VPD]
    foreach path $fa_paths {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {
            error "Unavailable object $path"
        }
    }
    puts FMA_ARB_PROBE_READY
    run
} failure]} {
    puts "FMA_ARB_PROBE_ERROR $failure"
    exit 1
}
