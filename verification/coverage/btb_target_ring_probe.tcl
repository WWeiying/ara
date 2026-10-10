# Observe only: no force, deposited value, reset, or RTL edits.
set core ara_tb.dut.i_ara_soc.i_system.i_ariane
set btb ${core}.i_frontend.btb_gen.i_btb
set objects [list ara_tb.clk ara_tb.rst_n ${core}.noc_req_o ${core}.noc_resp_i \
    ${btb}.btb_update_i ${btb}.update_pc ${btb}.update_row_index ${btb}.debug_mode_i \
    ${btb}.flush_bp_i ${core}.i_frontend.resolved_branch_i]
if {[catch {
    set fid [dump -file btb-target-ring.vpd -type VPD]
    foreach path $objects {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
        puts "BTB_RING_OBJECT $path"
    }
    puts "BTB_RING_READY"
    run
} failure]} {
    puts "BTB_RING_ERROR $failure"
    exit 1
}
