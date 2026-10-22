onerror {quit}
set fid [dump -file epoch.fsdb -type FSDB]
dump -add {ara_tb.clk} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.cycle_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.mfpu_reduction_any_active} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.mfpu_reduction_global_any_active} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_red_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_state_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vinsn_issue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.first_op_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_in_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_in_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_out_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_out_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_ex_flag} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.fpu_gen.reduction_fflags_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.reduction_any_active_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.sldu_transactions_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.sldu_mfpu_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.sldu_mfpu_ready_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_red_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_red_ready_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_vinsn_done_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_result_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_result_gnt_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.mfpu_result_wdata_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_state_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vinsn_issue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.first_op_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_in_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_in_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_out_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_out_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_ex_flag} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.fpu_gen.reduction_fflags_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.reduction_any_active_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.sldu_transactions_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.sldu_mfpu_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.sldu_mfpu_ready_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_red_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_red_ready_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_vinsn_done_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_result_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_result_gnt_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.mfpu_result_wdata_o} -aggregates -fid $fid
dump -disable -fid $fid
run -absolute 7000ns
dump -enable -fid $fid
run -absolute 7400ns
dump -disable -fid $fid
dump -flush $fid
run
quit
