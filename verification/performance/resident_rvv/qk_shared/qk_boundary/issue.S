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
    .globl qk_dest_set
qk_dest_set:
    li t0, 256
    vsetvli zero, t0, e32, m8, ta, ma
    vle32.v v0, (a0)
    addi t1, a0, 1024
    li t0, 128
    vsetvli zero, t0, e32, m4, ta, ma
    vle32.v v28, (t1)
    ret

    // Same observation ABI and machine trap handler as the frozen PV test.
    // a0=control a1=rm a2=vstart a3=bad a4=out a5=T a6=H a7=mode.
    .globl qk_issue
    .type qk_issue,@function
qk_issue:
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
    la t6, qk_fault_pc
    li t1, 5
    bne s4, t1, .Lrs2
    la t6, qk_bad_rd_pc
.Lrs2:
    li t1, 6
    bne s4, t1, .Lrd28
    la t6, qk_bad_rs2_pc
.Lrd28:
    li t1, 7
    bne s4, t1, .Lchosen
    la t6, qk_rd28_pc
.Lchosen:
    sd t6, 96(t0)
    la t1, qk_resume
    sd t1, 104(t0)
    sd a3, 88(t0)
    li t1, 1
    bne s4, t1, .Lvill
    vsetivli zero, 0, e8, m1, ta, ma
.Lvill:
    li t1, 2
    bne s4, t1, qk_read_before_vl
    li t1, -1
    vsetvl zero, zero, t1
    .globl qk_read_before_vl
qk_read_before_vl:
    csrr t1, vl
    sd t1, 136(t0)
    .globl qk_read_before_vtype
qk_read_before_vtype:
    csrr t1, vtype
    sd t1, 144(t0)
    csrw frm, a1
    csrw vstart, a2
    .globl qk_read_before_fcsr
qk_read_before_fcsr:
    frcsr t1
    sd t1, 0(t0)
    .globl qk_read_before_vstart
qk_read_before_vstart:
    csrr t1, vstart
    sd t1, 8(t0)
    li t1, 3
    bne s4, t1, .Lvsoff
    li t1, 0x6000
    csrc mstatus, t1
.Lvsoff:
    li t1, 4
    bne s4, t1, qk_read_before_mstatus
    li t1, 0x600
    csrc mstatus, t1
    .globl qk_read_before_mstatus
qk_read_before_mstatus:
    csrr t1, mstatus
    sd t1, 112(t0)
    jr t6
    .globl qk_fault_pc
qk_fault_pc:
    .word 0x0605705b
    j qk_resume
    .globl qk_bad_rd_pc
qk_bad_rd_pc:
    .word 0x0605715b
    j qk_resume
    .globl qk_bad_rs2_pc
qk_bad_rs2_pc:
    .word 0x0615705b
    j qk_resume
    .globl qk_rd28_pc
qk_rd28_pc:
    .word 0x06057e5b
    .globl qk_resume
qk_resume:
    la t0, boundary_observation
    .globl qk_read_after_mstatus
qk_read_after_mstatus:
    csrr t1, mstatus
    sd t1, 128(t0)
    li t2, 0x6600
    and t2, t2, s5
    csrs mstatus, t2
    .globl qk_read_after_vl
qk_read_after_vl:
    csrr t1, vl
    sd t1, 152(t0)
    .globl qk_read_after_vtype
qk_read_after_vtype:
    csrr t1, vtype
    sd t1, 160(t0)
    .globl qk_read_after_fcsr
qk_read_after_fcsr:
    frcsr t1
    sd t1, 64(t0)
    .globl qk_read_after_vstart
qk_read_after_vstart:
    csrr t1, vstart
    sd t1, 72(t0)
    csrwi vstart, 0
    csrwi frm, 0
    beqz s3, .Lsuccess
    la t1, boundary_dest_capture
    li t2, 256
    vsetvli zero, t2, e32, m8, ta, ma
    vse32.v v0, (t1)
    addi t1, t1, 1024
    li t2, 128
    vsetvli zero, t2, e32, m4, ta, ma
    vse32.v v28, (t1)
    j .Lstored
.Lsuccess:
    vsetvli zero, s1, e32, m2, ta, ma
    li t1, 7
    beq s4, t1, .Lhigh
    vse32.v v0, (s0)
    li t1, 1
    beq s2, t1, .Lstored
    addi t1, s0, 256
    vse32.v v2, (t1)
    j .Lstored
.Lhigh:
    vse32.v v28, (s0)
    li t1, 1
    beq s2, t1, .Lstored
    addi t1, s0, 256
    vse32.v v30, (t1)
.Lstored:
    fence rw, rw
    la t0, boundary_observation
    .globl qk_read_traps
qk_read_traps:
    ld a0, 16(t0)
    sd zero, 88(t0)
    ld s0, 0(sp)
    ld s1, 8(sp)
    ld s2, 16(sp)
    ld s3, 24(sp)
    ld s4, 32(sp)
    ld s5, 40(sp)
    addi sp, sp, 64
    .globl qk_issue_return
qk_issue_return:
    ret
    .size qk_issue, .-qk_issue

    // a0=already-prepared six-register PV source, a1=64 halfword output.
    .globl qk_pv_once
    .type qk_pv_once,@function
qk_pv_once:
    li t0, 384
    vsetvli zero, t0, e16, m8, ta, ma
    vle16.v v8, (a0)
    li a0, 0
    .globl qk_pv_pc
qk_pv_pc:
    .word 0x0485705b
    li t0, 64
    vsetvli zero, t0, e16, m2, ta, ma
    vse16.v v0, (a1)
    fence rw, rw
    frcsr a0
    ret
    .size qk_pv_once, .-qk_pv_once

    .globl qk_helper_observe
    .type qk_helper_observe,@function
qk_helper_observe:
    addi sp, sp, -16
    sd ra, 0(sp)
    call akv_experimental_resident_qk
    .globl qk_helper_fcsr_pc
qk_helper_fcsr_pc:
    frcsr a0
    ld ra, 0(sp)
    addi sp, sp, 16
    ret
    .size qk_helper_observe, .-qk_helper_observe
    .option pop
    .section .note.GNU-stack,"",@progbits
