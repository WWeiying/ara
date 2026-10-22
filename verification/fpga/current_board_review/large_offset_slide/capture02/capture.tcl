onerror {quit}
set fid [dump -file slide.fsdb -type FSDB]
dump -add {ara_tb.clk} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.sldu_addrgen_operand} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.sldu_operand_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.sldu_operand_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.read_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_m} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_m_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_m_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_first_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_read_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_write_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.issue_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.commit_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vrf_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.in_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.out_pnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.output_limit_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_operand} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_operand_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_operand_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sld_op_dst} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.mask_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.mask_valid_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.mask_ready_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.mask_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.mask_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.mask_ready_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.out_en_seq} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.out_en_flat} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.out_en} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_result_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_result_gnt_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_result_addr_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_result_wdata_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_result_be_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_lane_sequencer.operand_request} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_lane_sequencer.operand_request_push} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.requester_metadata_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.stall} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.vinsn_result_written_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.global_hazard_table_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.operand_requester_gnt} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_req_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_gnt_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_addr_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_wdata_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_be_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_id_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_gnt} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_addr} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_wdata} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_be} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.ldu_result_id} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.vrf_tgt_opqueue_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.vrf_addr_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.vrf_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.vrf_wen_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.vrf_be_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.vrf_wdata_o} -aggregates -fid $fid
dump -disable -fid $fid
run -absolute 103200ns
dump -enable -fid $fid
run -absolute 104000ns
dump -disable -fid $fid
dump -flush $fid
run
quit
