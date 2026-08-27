    .section .text.init
    .globl _start
_start:
    la sp, __stack_top
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la t0, qbs_trap_entry
    csrw mtvec, t0

    /* Enable architectural FP and vector state for qbexec. */
    li t0, ((3 << 13) | (3 << 9))
    csrs mstatus, t0
    call qbs_contract_main

1:  wfi
    j 1b

    .align 2
qbs_trap_entry:
    addi sp, sp, -32
    sd t0, 0(sp)
    sd t1, 8(sp)
    sd t2, 16(sp)
    sd t3, 24(sp)

    csrr t0, mcause
    la t1, qbs_trap_cause
    sd t0, 0(t1)
    csrr t0, mtval
    la t1, qbs_trap_tval
    sd t0, 0(t1)
    csrr t0, mepc
    addi t0, t0, 4
    csrw mepc, t0

    ld t0, 0(sp)
    ld t1, 8(sp)
    ld t2, 16(sp)
    ld t3, 24(sp)
    addi sp, sp, 32
    mret
