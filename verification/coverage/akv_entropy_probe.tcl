# Only observe accepted AKV read ranges; no force and no hierarchy-wide dump.
if {[catch {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine
    set fid [dump -file entropy-ranges.vpd -type VPD]
    foreach name {clk_i rst_ni read_range_fire read_range_vaddr read_range_bytes read_range_tag} {
        set object ${base}.${name}
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {error "Missing object $object"}
        puts "ENTROPY_RANGE_OBJECT $object"
    }
    puts "ENTROPY_RANGE_READY"
    run
} message]} {
    puts stderr "ENTROPY_RANGE_ERROR $message"
    exit 1
}
