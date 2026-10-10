# Read-only successor probe for the original gap112 ELF and build02.
# No force/deposit, no recursive memory dump, no unbounded run.
# ara_tb: 1 ns clock, first post-reset posedge at 15.5 ns.
# CSV samples pre-NBA cycle_q: capture events 54000 through 55999.
set system ara_tb.dut.i_ara_soc.i_system
set root ${system}.i_ara
set monitor ${system}.i_ara_commit_monitor
set required [list ara_tb.clk ara_tb.rst_n ara_tb.wall_cycle ${monitor}.cycle_q]

proc fof_objects {scope names} {
    global required
    foreach name $names {lappend required ${scope}.${name}}
}

fof_objects ${root}.i_masku {
    vinsn_issue vinsn_issue_valid iteration_cnt_q
    masku_operand_m_seq masku_operand_alu_seq masku_operand_vd_seq
    result_queue_active_mask_seq alu_result_vm_m
    background_data_init_seq result_queue_mask_seq out_vrf_word_valid
    masku_result_req_o masku_result_gnt_i masku_result_addr_o
    masku_result_wdata_o masku_result_be_o
    mask_o mask_valid_o mask_owner_id_o mask_first_element_o
}
fof_objects ${root}.i_vlsu.i_addrgen {
    pe_req_q addrgen_req addrgen_req_valid addrgen_req_ready
    state_q state_d mmu_req_o mmu_vaddr_o mmu_valid_i mmu_paddr_i
    mmu_exception_i mmu_exception_q
    axi_ar_o axi_ar_valid_o axi_ar_ready_i
    axi_aw_o axi_aw_valid_o axi_aw_ready_i
    axi_addrgen_queue axi_addrgen_queue_push axi_addrgen_queue_full
    axi_addrgen_queue_empty axi_addrgen_queue_pop
    axi_addrgen_req_o axi_addrgen_req_valid_o
    ldu_axi_addrgen_req_ready_i stu_axi_addrgen_req_ready_i
    addrgen_ack_o addrgen_exception_o addrgen_exception_vstart_o
    addrgen_fof_exception_o lsu_ex_flush_i
}
fof_objects ${root}.i_vlsu.i_vldu {
    pe_req_i pe_req_valid_i pe_req_ready_o
    vinsn_queue_q vinsn_issue_q vinsn_issue_valid vinsn_commit vinsn_commit_valid
    axi_addrgen_req_i axi_addrgen_req_valid_i axi_addrgen_req_ready_o
    axi_r_i axi_r_valid_i axi_r_ready_o
    mask_i mask_valid_i mask_owner_id_i mask_first_element_i mask_ready_o
    mask_word_q mask_word_valid mask_q mask_valid_q
    result_queue_q result_queue_d result_queue_valid_q result_queue_valid_d
    result_queue_write_pnt_q result_queue_read_pnt_q result_queue_cnt_q
    result_final_gnt_q
    ldu_result_req_o ldu_result_id_o ldu_result_addr_o
    ldu_result_wdata_o ldu_result_be_o ldu_result_gnt_i ldu_result_final_gnt_i
    issue_cnt_bytes_q commit_cnt_bytes_q axi_len_q axi_r_byte_pnt_q
    vrf_word_byte_pnt_q vrf_word_byte_cnt_q
    ldu_ex_state_q ldu_ex_state_d pe_resp_o load_complete_o
    ldu_current_burst_exception_o lsu_ex_flush_i lsu_ex_flush_q idle_o
}
fof_objects ${root}.i_vlsu.i_vstu {
    vinsn_issue_q stu_operand stu_operand_valid stu_operand_ready
    axi_w_o axi_w_valid_o axi_w_ready_i axi_b_i axi_b_valid_i axi_b_ready_o
    store_complete_o
}
fof_objects ${root}.i_vlsu {axi_req_o axi_resp_i}
fof_objects ${root}.i_sequencer {
    state_q ara_req_i ara_req_valid_i ara_req_ready_o
    pe_req_o pe_req_valid_o pe_req_ready_i pe_resp_i
    pe_vinsn_running_q vinsn_running_q vinsn_retired_q
    verify_vinsn_alloc verify_vinsn_done
    addrgen_ack_i addrgen_exception_i addrgen_exception_vstart_i
    addrgen_fof_exception_i lsu_current_burst_exception_i
    ara_resp_o ara_resp_valid_o
}
fof_objects ${root}.i_dispatcher {
    ara_resp_i ara_resp_valid_i acc_req_i acc_resp_o
    csr_vl_q csr_vstart_q csr_vtype_q lsu_ex_flush_o
    lsu_ex_flush_done_i load_complete_i
}
for {set lane 0} {$lane < 4} {incr lane} {
    set scope [format {%s.gen_lanes[%d].i_lane} $root $lane]
    fof_objects ${scope}.i_operand_requester {
        ldu_result_req_i ldu_result_gnt_o ldu_result_final_gnt_o
        masku_result_req_i masku_result_gnt_o
        vrf_req_o vrf_wen_o vrf_addr_o vrf_wdata_o vrf_be_o
        verify_wb_valid_o verify_wb_wdata_o verify_wb_be_o verify_wb_addr_o verify_wb_id_o
    }
    fof_objects ${scope}.i_vrf {rdata rdata_valid_q}
}

if {[catch {
    if {[file exists fof-build02-prefix.vpd]} {error "Refusing existing wave file"}
    # Fail before advancing time when required hierarchy is inaccessible.
    foreach path $required {show -type $path}
    puts FOF_PROBE_PREFLIGHT_READY
    run 54015 ns
    puts "FOF_PROBE_BEGIN cycle_q=[get ${monitor}.cycle_q -radix decimal]"
    set fid [dump -file fof-build02-prefix.vpd -type VPD]
    foreach path $required {
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {
            error "Unavailable required dump object $path"
        }
        puts "FOF_PROBE_CAPTURED $path"
    }
    run 2000 ns
    puts "FOF_PROBE_END cycle_q=[get ${monitor}.cycle_q -radix decimal]"
    dump -flush $fid
    dump -close $fid
    puts FOF_PROBE_WINDOW_COMPLETE_NOT_ARCHITECTURAL_PASS
} failure]} {
    puts "FOF_PROBE_ERROR $failure"
    exit 1
}
quit
