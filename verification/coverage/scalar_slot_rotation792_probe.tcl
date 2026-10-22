# Read-only LSU cancellation plus same-edge scoreboard allocation/flush evidence.
set core ara_tb.dut.i_ara_soc.i_system.i_ariane
set lsu ${core}.ex_stage_i.lsu_i
set sb ${core}.issue_stage_i.i_scoreboard
if {[catch {
    set fid [dump -file scalar-misalign.vpd -type VPD]
    foreach path [list ara_tb.clk ara_tb.rst_n \
        ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q \
        ${lsu}.lsu_ctrl ${lsu}.data_misaligned ${lsu}.cva6_misaligned_exception \
        ${lsu}.load_exception_o ${lsu}.store_exception_o \
        ${lsu}.load_valid_o ${lsu}.store_valid_o ${lsu}.load_trans_id_o ${lsu}.store_trans_id_o \
        ${lsu}.i_load_unit.ex_i ${lsu}.i_store_unit.ex_i \
        ${lsu}.i_load_unit.req_port_o ${lsu}.i_store_unit.st_valid \
        ${core}.commit_instr_id_commit ${core}.commit_ack \
        ${core}.csr_regfile_i.ex_i ${core}.csr_regfile_i.pc_i \
        ${core}.csr_regfile_i.mstatus_q ${core}.csr_regfile_i.priv_lvl_o ${core}.csr_regfile_i.eret_o \
        ${sb}.issue_pointer_q ${sb}.issue_pointer_n ${sb}.flush_i \
        ${sb}.flush_unissued_instr_i ${sb}.decoded_instr_valid_i ${sb}.decoded_instr_ack_o \
        ${sb}.decoded_instr_i ${sb}.issue_instr_o ${sb}.orig_instr_i] {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
    }
    puts SCALAR_MISALIGN_PROBE_READY
    run
} failure]} {
    puts "SCALAR_MISALIGN_PROBE_ERROR $failure"
    exit 1
}
