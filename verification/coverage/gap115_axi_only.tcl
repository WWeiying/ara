# Documented UCLI VPD dump; four explicit objects, no hierarchy or force.
if {[catch {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara
    set fid [dump -file axi-only.vpd -type VPD]
    foreach name {clk_i rst_ni axi_req_o axi_resp_i} {
        set object ${base}.${name}
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {
            error "No dump object added: $object"
        }
        puts "GAP115_AXI_OBJECT $object"
    }
    puts "GAP115_AXI_FOUR_OBJECTS_READY"
    run
} message]} {
    puts stderr "GAP115_AXI_CAPTURE_ERROR $message"
    exit 1
}
