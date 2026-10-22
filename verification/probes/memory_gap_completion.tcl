# Focused completion accounting, using the existing debug-enabled image.
set a ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_accelerator.i_acc_dispatcher
set d ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher
run 16500 ns
set previous {}
for {set cycle 16500} {$cycle < 21800} {incr cycle} {
    set values {}
    foreach signal [list $a.acc_disp_loads_pending $a.acc_ld_disp \
        $d.acc_resp_o.load_complete $d.load_complete_i $d.load_complete_q \
        $d.load_zero_vl $d.pending_seg_mem_op_q $d.is_segment_mem_op \
        $d.state_q $d.ara_idle_i $d.acc_req_i.insn $d.csr_vl_q] {
        lappend values [get $signal]
    }
    if {$values ne $previous} {puts "COMPLETE_PROBE $cycle $values"}
    set previous $values
    run 1 ns
}
quit
