onerror {quit}
set fid [dump -file indexed_first_round.fsdb -type FSDB]
set top ara_tb.dut.i_ara_soc.i_system
set ara $top.i_ara
dump -add {ara_tb.clk} -fid $fid
dump -add $top.i_ara_commit_monitor.cycle_q -aggregates -fid $fid
foreach p {acc_req_i acc_resp_o state_q csr_vstart_q csr_vtype_q ara_req ara_req_valid ara_req_ready_i eew_q source_snapshot_valid_q source_snapshot_vs_q source_snapshot_eew_q} {
    dump -add $ara.i_dispatcher.$p -aggregates -fid $fid
}
foreach p {pe_req_q idx_op_cnt_q idx_vaddr idx_vaddr_valid_q idx_vaddr_ready_d idx_final_vaddr_q mmu_req_o mmu_vaddr_o mmu_valid_i mmu_paddr_i mmu_exception_i addrgen_exception_o addrgen_exception_vstart_o} {
    dump -add $ara.i_vlsu.i_addrgen.$p -aggregates -fid $fid
}
foreach p {pe_req_i pe_req_valid_i pe_req_ready_o ldu_ex_state_q result_queue_cnt_q result_final_gnt_q ldu_result_req_o ldu_result_gnt_i ldu_result_final_gnt_i ldu_result_addr_o ldu_result_wdata_o ldu_result_be_o pe_resp_o} {
    dump -add $ara.i_vlsu.i_vldu.$p -aggregates -fid $fid
}
foreach p {ara_req_i ara_req_valid_i ara_req_ready_o ara_resp_o ara_resp_valid_o pe_resp_i verify_vinsn_done} {
    dump -add $ara.i_sequencer.$p -aggregates -fid $fid
}
for {set i 0} {$i < 4} {incr i} {
    set lane [format {%s.gen_lanes[%d].i_lane} $ara $i]
    foreach p {source_snapshot_q source_snapshot_capture_q source_snapshot_capture_index_q source_snapshot_capture_last_q source_snapshot_replay_valid source_snapshot_replay_index operand_request operand_request_valid operand_request_ready vrf_operand vrf_operand_valid operand_queue_input operand_queue_input_valid} {
        dump -add $lane.$p -aggregates -fid $fid
    }
    foreach p {operand_requester_gnt requester_metadata_q operand_queue_cmd_o vrf_req_o vrf_addr_o vrf_tgt_opqueue_o vrf_wen_o vrf_wdata_o vrf_be_o} {
        dump -add $lane.i_operand_requester.$p -aggregates -fid $fid
    }
}
puts INDEXED_PROFILE_OPEN_AT_START
run -absolute 1000000ns
dump -disable -fid $fid
dump -flush $fid
puts INDEXED_PROFILE_CLOSED_AT_1000000NS
run
quit
