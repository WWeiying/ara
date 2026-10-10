# Read-only CSR owner observation; no force/deposit or state modifications.
set core ara_tb.dut.i_ara_soc.i_system.i_ariane
set csr ${core}.csr_regfile_i
set buffer ${core}.ex_stage_i.csr_buffer_i
if {[catch {
    set fid [dump -file csr-owner.vpd -type VPD]
    foreach path [list ara_tb.clk ara_tb.rst_n \
        ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q \
        ${core}.csr_commit_commit_ex ${csr}.commit_ack_i ${csr}.pc_i \
        ${csr}.commit_instr_i.trans_id ${csr}.csr_op_i ${csr}.csr_addr_i \
        ${csr}.csr_wdata_i ${csr}.csr_rdata_o ${csr}.priv_lvl_o \
        ${csr}.mstatus_q.mprv ${csr}.mstatus_q.mie \
        ${buffer}.csr_valid_i ${buffer}.csr_ready_o ${buffer}.csr_commit_i ${buffer}.csr_reg_q.valid \
        ${buffer}.fu_data_i.trans_id ${buffer}.fu_data_i.operand_a \
        ${buffer}.fu_data_i.operand_b ${buffer}.flush_i] {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
    }
    puts CSR_OWNER_PROBE_READY
    run
} failure]} {
    puts "CSR_OWNER_PROBE_ERROR $failure"
    exit 1
}
