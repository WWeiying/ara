onerror {quit}
set fid [dump -file comparison.vpd -type VPD]
dump -add {ara_tb.clk} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.reshuffle_req_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.reshuffle_req_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_ready_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_q[8]} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_q[16]} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.op} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vd} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vs1} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vs2} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.eew_vs1} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.eew_vs2} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vtype.vsew} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req.op} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req.vd} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req.vs1} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req.vs2} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req.eew_vs1} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req.eew_vs2} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req.vtype.vsew} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.id} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.vtype.vsew} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.operand_b} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_in_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_in_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_out_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_out_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_processed_result} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu.vfpu_tag_out.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.id} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.vtype.vsew} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.operand_b} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_in_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_in_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_out_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_out_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_processed_result} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_vfus.i_vmfpu.vfpu_tag_out.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.id} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.vtype.vsew} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.operand_b} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vfpu_in_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vfpu_in_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vfpu_out_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vfpu_out_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vfpu_processed_result} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_vfus.i_vmfpu.vfpu_tag_out.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.id} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.vtype.vsew} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.operand_b} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vfpu_in_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vfpu_in_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vfpu_out_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vfpu_out_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vfpu_processed_result} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_vfus.i_vmfpu.vfpu_tag_out.operand_a} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrf_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.fp_compare_nv_seq} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_active_mask_seq} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_alu_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_alu_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.fflags_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.fflags_valid_o} -aggregates -fid $fid
dump -disable -fid $fid
run -absolute 15700ns
dump -enable -fid $fid
run -absolute 17000ns
dump -disable -fid $fid
dump -flush $fid
run
quit
