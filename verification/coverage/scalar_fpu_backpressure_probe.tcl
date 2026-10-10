# Observation only: no force/deposit/stop and no DUT state changes.
set bp ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.fpu_gen.fpu_i
if {[catch {
    set fid [dump -file scalar-fpu-backpressure.vpd -type VPD]
    foreach path [list ara_tb.clk ara_tb.rst_n ${bp}.flush_i ${bp}.state_q \
        ${bp}.fpu_valid_i ${bp}.fpu_ready_o ${bp}.fpu_gen.fpu_in_ready \
        ${bp}.fpu_gen.hold_inputs ${bp}.fpu_gen.use_hold \
        ${bp}.fpu_gen.operand_a_d ${bp}.fpu_gen.operand_b_d \
        ${bp}.fpu_gen.operand_a_q ${bp}.fpu_gen.operand_b_q] {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
    }
    puts BP_PROBE_READY
    run
} failure]} {
    puts "BP_PROBE_ERROR $failure"
    exit 1
}
