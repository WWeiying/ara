# Read-only exact AKV command/capture/fault/range/AR profile.
if {[catch {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine
    set fid [dump -file entropy-ranges.vpd -type VPD]
    foreach name {clk_i rst_ni command_fire command_i command_tile_start_i requested_tile_start_q fault_valid_o success_valid_o fault_is_validation_o validation_error_o context_ready_o mmu_exception_valid_i read_range_fire read_range_vaddr read_range_bytes read_range_tag axi_ar_valid_o axi_ar_ready_i i_read_engine.ar_addr_q} {
        set object ${base}.${name}
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {error "Missing object $object"}
        puts "TILE_RANGE_OBJECT $object"
    }
    puts "TILE_RANGE_READY"
    run
} message]} {
    puts stderr "TILE_RANGE_ERROR $message"
    exit 1
}
