# Read-only two-bank pending profile. No internal forces or coverage changes.
if {[catch {
    set root ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine
    set wave qbs-pending-two-phase.vpd
    set fid [dump -file $wave -type VPD]
    set objects [list ara_tb.clk ara_tb.rst_n]
    foreach name {
        range_valid_i range_ready_o range_vaddr_i range_bytes_i
        data_valid_o data_ready_i data_offset_o data_strb_o data_tag_o
        response_head beat_take_bytes range_fifo_count_q response_drain_q
    } {lappend objects ${root}.i_read_engine.${name}}
    foreach bank {0 1} {
        set adapter ${root}.i_compute_engine.i_block_adapter_bank${bank}
        set payload ${adapter}.i_payload_buffer
        foreach name {
            activation_write_valid_i activation_write_ready_o activation_write_offset_i
            activation_write_context_i activation_ingress_count_q activation_ingress_push
            activation_pending_q_valid activation_pending_q activation_source_valid
            activation_remaining activation_consumed clear_activation_i
            weight_pending_q_valid weight_pending_q weight_source_valid
            weight_remaining weight_consumed clear_weight_i
        } {lappend objects ${adapter}.${name}}
        foreach row {0 1 2 3} {
            foreach slot {0 1} {
                foreach field {candidate selected_word word_match} {
                    set suffix [format {gen_write_merge[%d].gen_bank_plane[2].gen_bank_row[%d].%s} $slot $row $field]
                    lappend objects ${payload}.${suffix}
                }
            }
            set suffix [format {gen_write_merge[0].gen_bank_plane[2].gen_bank_row[%d].gen_byte_merge[5].hit} $row]
            lappend objects ${payload}.${suffix}
        }
    }
    foreach object $objects {
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {error "Missing exact object $object"}
        puts "QBS_TWO_PHASE_OBJECT $object"
    }
    puts "QBS_TWO_PHASE_PROBE_READY"
    while {1} {
        run 100 ns
        if {[file exists $wave] && [file size $wave] >= 66060288} {error "Focused VPD capacity boundary"}
    }
} failure]} {
    puts stderr "QBS_TWO_PHASE_PROBE_REJECT $failure"
    exit 1
}
