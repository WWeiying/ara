onerror {quit}
set fid [dump -file selected.fsdb -type FSDB]
dump -add {ara_tb.clk} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_req_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vl_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vstart_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_valid_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_ready_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_lane_sequencer.pe_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_lane_sequencer.pe_req_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_lane_sequencer.pe_req_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_lane_sequencer.vfu_operation_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_lane_sequencer.vfu_operation_valid_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.vfu_operation_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.vfu_operation_valid_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_ready_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.vinsn_issue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.vinsn_issue_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.issue_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.valu_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.valu_result} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.result_write} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_result_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_result_gnt_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_result_id_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_result_addr_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_result_be_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_result_wdata_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_valu.alu_vinsn_done_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.decode_blocked} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.layout_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.reshuffle_req_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.reshuffle_req_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_q[24]} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_d[24]} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.vs_buffer_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_old_buffer_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.eew_new_buffer_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.rs_lmul_cnt_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.rs_lmul_cnt_limit_q} -aggregates -fid $fid
run -absolute 50000ns
dump -disable -fid $fid
dump -flush $fid
run
quit
