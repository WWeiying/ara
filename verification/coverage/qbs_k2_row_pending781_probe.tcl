# Read-only focused producer/arbitration profile. Missing objects reject capture.
if {[catch {
    set root ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine
    set adapter ${root}.i_compute_engine.i_block_adapter_bank0
    set payload ${adapter}.i_payload_buffer
    set wave qbs-k2-row-pending.vpd
    set fid [dump -file $wave -type VPD]
    set objects [list ara_tb.clk ara_tb.rst_n]
    foreach name {
        range_valid_i range_ready_o range_vaddr_i range_bytes_i
        data_valid_o data_ready_i data_offset_o data_strb_o data_tag_o
        response_head beat_take_bytes range_fifo_count_q response_drain_q
    } {lappend objects ${root}.i_read_engine.${name}}
    foreach name {
        activation_write_valid_i activation_write_ready_o activation_write_offset_i
        activation_write_context_i activation_ingress_count_q activation_ingress_push
        activation_pending_q_valid activation_pending_q activation_source
        activation_source_valid activation_pending_location_q activation_pending_target_q
        activation_pending_multiword activation_remaining activation_consumed
        clear_activation_i
    } {lappend objects ${adapter}.${name}}
    # Braces keep native array brackets literal, never Tcl command substitution.
    foreach name {
        {write_req[0][2][2]} {write_addr[0][2][2]}
        {write_req[1][2][2]} {write_addr[1][2][2]}
        {gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].candidate}
        {gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].selected_word}
        {gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].word_match}
        {gen_write_merge[1].gen_bank_plane[2].gen_bank_row[2].candidate}
        {gen_write_merge[1].gen_bank_plane[2].gen_bank_row[2].selected_word}
        {gen_write_merge[1].gen_bank_plane[2].gen_bank_row[2].word_match}
        {gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].gen_byte_merge[5].hit}
    } {lappend objects ${payload}.${name}}
    foreach object $objects {
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {
            error "Missing exact object $object"
        }
        puts "QBS_PENDING_OBJECT $object"
    }
    puts "QBS_PENDING_PROBE_READY"
    while {1} {
        run 100 ns
        if {[file exists $wave] && [file size $wave] >= 66060288} {
            error "Focused VPD capacity boundary; incomplete capture rejected"
        }
    }
} failure]} {
    puts stderr "QBS_PENDING_PROBE_REJECT $failure"
    exit 1
}
