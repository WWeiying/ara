// New test-only glue. All successful stores cover active elements only.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl boundary_fill
boundary_fill:
    fence rw, rw
    .word 0x00b5605b
    ret
    .globl boundary_release
boundary_release:
    .word 0x0000505b
    ret

    .globl boundary_dest_set
boundary_dest_set:
    li t0, 128
    vsetvli zero, t0, e32, m4, ta, ma
    vle32.v v0, (a0)
    ret

    .globl boundary_mixed_load
boundary_mixed_load:
    li t0, 192
    vsetvli zero, t0, e32, m8, ta, ma
    vle32.v v8, (a0)
    li t0, 32
    vsetvli zero, t0, e64, m2, ta, ma
    vle64.v v14, (a1)
    // The dependent drain in C must also read v8 at EW32, not reshape it.
    li t0, 192
    vsetvli zero, t0, e32, m8, ta, ma
    ret

    .globl boundary_mixed_capture
boundary_mixed_capture:
    // Read guards in their original EEW before any source diagnostic access.
    li t0, 32
    vsetvli zero, t0, e64, m2, ta, ma
    vse64.v v14, (a1)
    li t0, 384
    vsetvli zero, t0, e16, m8, ta, ma
    vse16.v v8, (a0)
    vmv.x.s t0, v8
    fence rw, rw
    ret

    // a0=control a1=issue_frm a2=issue_vstart a3=expect_trap
    // a4=output (512B/head), a5=D, a6=H, a7=boundary mode.
    .globl boundary_issue
    .type boundary_issue,@function
boundary_issue:
    addi sp, sp, -64
    sd s0, 0(sp)
    sd s1, 8(sp)
    sd s2, 16(sp)
    sd s3, 24(sp)
    sd s4, 32(sp)
    sd s5, 40(sp)
    mv s0, a4
    mv s1, a5
    mv s2, a6
    mv s3, a3
    mv s4, a7
    csrr s5, mstatus
    la t0, boundary_observation
    la t6, boundary_pv_fault_pc
    li t1, 5
    bne s4, t1, .Lchoose_vs2
    la t6, boundary_pv_rd2_pc
.Lchoose_vs2:
    li t1, 6
    bne s4, t1, .Lchoose_alias
    la t6, boundary_pv_vs2v4_pc
.Lchoose_alias:
    li t1, 7
    bne s4, t1, .Lchosen
    la t6, boundary_pv_alias_pc
.Lchosen:
    sd t6, 96(t0)
    la t1, .Lboundary_resume
    sd t1, 104(t0)
    sd a3, 88(t0)
    li t1, 1
    bne s4, t1, .Lmaybe_vill
    vsetivli zero, 0, e8, m1, ta, ma
.Lmaybe_vill:
    li t1, 2
    bne s4, t1, .Lcapture_config
    li t1, -1
    vsetvl zero, zero, t1
.Lcapture_config:
    csrr t1, vl
    sd t1, 136(t0)
    csrr t1, vtype
    sd t1, 144(t0)
    csrw frm, a1
    csrw vstart, a2
    frcsr t1
    sd t1, 0(t0)
    csrr t1, vstart
    sd t1, 8(t0)
    li t1, 3
    bne s4, t1, .Lmaybe_vsoff
    li t1, 0x6000
    csrc mstatus, t1
.Lmaybe_vsoff:
    li t1, 4
    bne s4, t1, .Lcapture_status
    li t1, 0x600
    csrc mstatus, t1
.Lcapture_status:
    csrr t1, mstatus
    sd t1, 112(t0)
    jr t6
    .globl boundary_pv_fault_pc
boundary_pv_fault_pc:
    .word 0x0485705b
    j .Lboundary_resume
    .globl boundary_pv_rd2_pc
boundary_pv_rd2_pc:
    .word 0x0485715b
    j .Lboundary_resume
    .globl boundary_pv_vs2v4_pc
boundary_pv_vs2v4_pc:
    .word 0x0445705b
    j .Lboundary_resume
    .globl boundary_pv_alias_pc
boundary_pv_alias_pc:
    .word 0x0485745b
.Lboundary_resume:
    // Capture the untouched trap-time CSR state before software recovery.
    la t0, boundary_observation
    csrr t1, mstatus
    sd t1, 128(t0)
    // FS/VS-off traps must restore access before reading FP/vector CSRs.
    li t2, 0x6600
    and t2, t2, s5
    csrs mstatus, t2
    csrr t1, vl
    sd t1, 152(t0)
    csrr t1, vtype
    sd t1, 160(t0)
    frcsr t1
    sd t1, 64(t0)
    csrr t1, vstart
    sd t1, 72(t0)
    csrwi vstart, 0
    csrwi frm, 0
    beqz s3, .Lboundary_success_store
    // Failure must retain the entire old EW32 destination interpretation.
    // This is the very first vector operation after the faulting instruction.
    la t1, boundary_dest_capture
    li t2, 128
    vsetvli zero, t2, e32, m4, ta, ma
    vse32.v v0, (t1)
    j .Lboundary_stores_done
.Lboundary_success_store:
    vsetvli zero, s1, e16, m2, ta, ma
    vse16.v v0, (s0)
    li t1, 1
    beq s2, t1, .Lboundary_stores_done
    addi t1, s0, 512
    vse16.v v2, (t1)
.Lboundary_stores_done:
    vmv.x.s t1, v0
    fence rw, rw
    la t0, boundary_observation
    ld a0, 16(t0)
    sd zero, 88(t0)
    ld s0, 0(sp)
    ld s1, 8(sp)
    ld s2, 16(sp)
    ld s3, 24(sp)
    ld s4, 32(sp)
    ld s5, 40(sp)
    addi sp, sp, 64
    ret
    .size boundary_issue, .-boundary_issue
    .option pop
    .section .note.GNU-stack,"",@progbits
