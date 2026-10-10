# Read-only accepted command/MMU/AR profile; no force, exclusions or reset.
if {[catch {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine
    set fid [dump -file entropy-ranges.vpd -type VPD]
    foreach name {clk_i rst_ni command_fire command_i command_id_i command_vd_i command_selector_i command_descriptor_address_i command_tile_start_i fault_valid_o success_valid_o context_ready_o read_range_fire read_range_vaddr read_range_bytes read_range_tag axi_ar_valid_o axi_ar_ready_i i_read_engine.en_ld_st_translation_i i_read_engine.mmu_req_o i_read_engine.mmu_valid_i i_read_engine.mmu_exception_valid_i i_read_engine.mmu_vaddr_o i_read_engine.mmu_paddr_i i_read_engine.translation_complete i_read_engine.plan_state_q i_read_engine.ar_addr_q i_read_engine.ar_cursor_vaddr_q i_read_engine.ar_chunk_bytes_q} {
        set object ${base}.${name}
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {error "Missing object $object"}
        puts "AKV_ALIAS_OBJECT $object"
    }
    puts "AKV_ALIAS_READY"
    run
} message]} {
    puts stderr "AKV_ALIAS_ERROR $message"
    exit 1
}
