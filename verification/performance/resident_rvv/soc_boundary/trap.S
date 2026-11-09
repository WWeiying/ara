// Private machine trap entry. Never print or execute FP/vector instructions here.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl rvtest_init
rvtest_init:
    li t0, 0x1800
    csrs mstatus, t0
    la t0, boundary_trap
    csrw mtvec, t0
    ret

    .globl boundary_trap
    .type boundary_trap,@function
boundary_trap:
    addi sp, sp, -32
    sd t0, 0(sp)
    sd t1, 8(sp)
    sd t2, 16(sp)
    sd t3, 24(sp)
    la t0, boundary_observation
    csrr t1, mcause
    sd t1, 24(t0)
    csrr t2, mepc
    sd t2, 32(t0)
    csrr t3, mstatus
    sd t3, 120(t0)
    li t1, 0x6000
    and t1, t1, t3
    beqz t1, .Ltrap_minimal
    li t1, 0x600
    and t1, t1, t3
    beqz t1, .Ltrap_minimal
    csrr t3, mtval
    sd t3, 40(t0)
    frcsr t3
    sd t3, 48(t0)
    csrr t3, vstart
    sd t3, 56(t0)
    li t3, 1
    sd t3, 168(t0)
.Ltrap_minimal:
    ld t1, 24(t0)
    li t3, 2
    bne t1, t3, .Lunexpected
    ld t3, 96(t0)
    bne t2, t3, .Lunexpected
    ld t3, 88(t0)
    li t1, 1
    bne t3, t1, .Lunexpected
    ld t3, 16(t0)
    bnez t3, .Lunexpected
    sd t1, 16(t0)
    sd zero, 88(t0)
    ld t1, 104(t0)
    csrw mepc, t1
    ld t0, 0(sp)
    ld t1, 8(sp)
    ld t2, 16(sp)
    ld t3, 24(sp)
    addi sp, sp, 32
    mret
.Lunexpected:
    li t1, 1
    sd t1, 80(t0)
    // Unknown traps cannot resume through a stale continuation or fake DONE.
    la t1, _fail
    csrw mepc, t1
    li a0, 1
    addi sp, sp, 32
    mret
    .size boundary_trap, .-boundary_trap
    .option pop
    .section .note.GNU-stack,"",@progbits
