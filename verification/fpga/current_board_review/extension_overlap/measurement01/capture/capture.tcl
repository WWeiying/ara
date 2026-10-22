onerror {quit}
set fid [dump -file selected.fsdb -type FSDB]
dump -add {ara_tb.clk} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_req_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.verify_active_insn_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.verify_front_active_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vl_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vtype_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vstart_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.backend_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_ready_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_idle_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.sldu_idle_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_q[24]} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_q[25]} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.reshuffle_req_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.reshuffle_req_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.legal_widen_overlap} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.masked_widen_layout_conflict} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.source_snapshot_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.source_snapshot_resolves_widen} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.rs_lmul_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.rs_lmul_cnt_limit_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.vs_buffer_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_old_buffer_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_new_buffer_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.verify_vinsn_done} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.global_hazard_table_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.pe_req_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.pe_req_valid_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.requester_metadata_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.operand_request_valid_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.source_lifetime_active} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.lane_operand_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.operand_gnt} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_requester.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_requester.requester_metadata_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_requester.operand_request_valid_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_requester.source_lifetime_active} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_requester.lane_operand_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_requester.operand_gnt} -aggregates -fid $fid
dump -disable -fid $fid
run -absolute 20050ns
dump -enable -fid $fid
run -absolute 21050ns
dump -disable -fid $fid
dump -flush $fid
quit
