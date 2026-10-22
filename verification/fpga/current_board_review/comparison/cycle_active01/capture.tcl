onerror {quit}
set fid [dump -file comparison.fsdb -type FSDB]
dump -add {ara_tb.clk} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.fflags_ex} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.fflags_ex_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfu_operation_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfu_operation_valid_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vinsn_issue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vinsn_issue_q_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.issue_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.issue_be} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.operand_b} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_in_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_in_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_out_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_out_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_tag_in} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_tag_out} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_ex_flag_fn} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_ex_flag} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fflags_ex_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fflags_ex_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mask_operand_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mask_operand_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mask_operand_ready_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fpu_gen.vfpu_simd_mask} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_status} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_masks} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.out_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.out_ready_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_m_seq} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_alu_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_alu_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_m_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_m_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_vd_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_full} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_active_mask_seq} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.alu_result_compressed_seq} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.in_ready_cnt_en} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.iteration_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrf_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrf_pnt_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.issue_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_result_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_result_gnt_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.pe_resp_o} -aggregates -fid $fid
dump -disable -fid $fid
run -absolute 16200ns
dump -enable -fid $fid
run -absolute 16600ns
dump -disable -fid $fid
dump -flush $fid
run
quit
