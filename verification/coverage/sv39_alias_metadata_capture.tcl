# Read-only, explicit metadata/AXI profile. No force, reset, hierarchy traversal or FSDB.
if {[catch {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara
    set fifo ${base}.i_vlsu.i_vstu.i_store_b_metadata
    set objects [list ${base}.clk_i ${base}.rst_ni ${base}.acc_mmu_en_q \
        ${base}.axi_req_o ${base}.axi_resp_i ${fifo}.push_i ${fifo}.full_o \
        ${fifo}.flush_i ${fifo}.write_pointer_q ${fifo}.data_i \
        ${base}.i_vlsu.i_addrgen.axi_addrgen_req_o]
    set fid [dump -file alias-metadata.vpd -type VPD]
    foreach object $objects {
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {
            error "Missing precise capture object: $object"
        }
        puts "ALIAS_METADATA_OBJECT $object"
    }
    puts "ALIAS_METADATA_PROFILE_READY_11"
    run
} message]} {
    puts stderr "ALIAS_METADATA_CAPTURE_ERROR $message"
    exit 1
}
