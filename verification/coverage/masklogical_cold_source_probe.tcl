if {[catch {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku
    set fid [dump -file masklogical-cold.vpd -type VPD]
    foreach name {
        clk_i rst_ni vinsn_issue_valid vinsn_issue.op
        vinsn_issue.vs1 vinsn_issue.vs2
        masku_operand_alu_seq masku_operand_m_seq alu_result_vm_m
        masku_operand_alu_valid masku_operand_m_valid masku_operand_alu_ready
    } {
        set n [dump -add ${base}.${name} -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $n] || $n <= 0} {error "Missing ${base}.${name}"}
        puts "MASKLOGICAL_OBJECT ${base}.${name}"
    }
    puts "MASKLOGICAL_COLD_PROBE_READY"
    run 250000 ns
    dump -close $fid
    puts "MASKLOGICAL_COLD_PROBE_CLOSED"
    run
} failure]} {
    puts stderr "MASKLOGICAL_PROBE_REJECT $failure"
    exit 1
}
