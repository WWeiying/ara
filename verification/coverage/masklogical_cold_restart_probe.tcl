# Full native matrix: cold-source proof and focused restart capture in one run.
# Do not quit after the restart window; all 68 software cases must complete.
set root ara_tb.dut.i_ara_soc.i_system.i_ara
set monitor ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor
set required [list ara_tb.clk ara_tb.rst_n ${monitor}.cycle_q]
proc ml_full_objects {scope names} {
    global required
    foreach name $names {lappend required ${scope}.${name}}
}
ml_full_objects ${root}.i_masku {
    pe_req_i pe_req_valid_i pe_req_ready_o pe_resp_o
    vinsn_issue vinsn_issue_valid issue_cnt_q processing_cnt_q commit_cnt_q read_cnt_q
    iteration_cnt_q delta_elm_q
    in_ready_cnt_q in_ready_threshold_q in_m_ready_cnt_q in_m_ready_threshold_q
    out_valid_cnt_q out_valid_threshold_q
    masku_operand_alu_valid masku_operand_alu_ready
    masku_operand_m_valid masku_operand_m_ready
    masku_operand_vd_valid masku_operand_vd_ready
    result_queue_cnt_q result_queue_full
    masku_result_req_o masku_result_gnt_i masku_result_final_gnt_i
    masku_result_addr_o masku_result_be_o
}
for {set lane 0} {$lane < 4} {incr lane} {
    set scope [format {%s.gen_lanes[%d].i_lane} $root $lane]
    ml_full_objects ${scope}.i_lane_sequencer {
        pe_req pe_req_valid pe_req_ready
        operand_request operand_request_push operand_request_o
        operand_request_valid_o operand_request_ready_i
        vfu_operation_o vfu_operation_valid_o
    }
    ml_full_objects ${scope}.i_operand_requester {
        requester_metadata_q state_q stall operand_queue_ready_i
        operand_queue_cmd_o operand_queue_cmd_valid_o
    }
    ml_full_objects ${scope}.i_vfus.i_valu {
        vinsn_issue_q issue_cnt_q alu_operand_valid_i alu_operand_ready_o
        result_queue_cnt_q mask_operand_valid_o mask_operand_ready_i
    }
}
if {[catch {
    foreach path $required {show -type $path}
    if {[file exists masklogical-cold.vpd] || [file exists masklogical-restart.vpd]} {
        error "Refusing existing waveform files"
    }
    set base ${root}.i_masku
    set fid [dump -file masklogical-cold.vpd -type VPD]
    foreach name {
        clk_i rst_ni vinsn_issue_valid vinsn_issue.op
        vinsn_issue.vs1 vinsn_issue.vs2
        masku_operand_alu_seq masku_operand_m_seq alu_result_vm_m
        masku_operand_alu_valid masku_operand_m_valid masku_operand_alu_ready
    } {
        set n [dump -add ${base}.${name} -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $n] || $n <= 0} {error "Missing ${base}.${name}"}
        puts "MASKLOGICAL_OBJECT ${base}.${name}"
    }
    puts MASKLOGICAL_COLD_PROBE_READY
    run 250000 ns
    dump -flush $fid
    dump -close $fid
    puts MASKLOGICAL_COLD_PROBE_CLOSED
    run 545 ns
    puts "MASKLOGICAL_RESTART_BEGIN cycle_q=[get ${monitor}.cycle_q -radix decimal]"
    set fid [dump -file masklogical-restart.vpd -type VPD]
    foreach path $required {
        set n [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $n] || $n <= 0} {error "Missing $path"}
    }
    run 220 ns
    puts "MASKLOGICAL_RESTART_END cycle_q=[get ${monitor}.cycle_q -radix decimal]"
    dump -flush $fid
    dump -close $fid
    puts MASKLOGICAL_RESTART_CAPTURE_COMPLETE_CONTINUING_FULL_MATRIX
    run
} failure]} {
    puts "MASKLOGICAL_PROBE_REJECT $failure"
    exit 1
}
