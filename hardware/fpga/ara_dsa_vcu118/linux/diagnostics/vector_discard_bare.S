.section .text.init
.globl _start
_start:
    csrw mie, zero
    csrw satp, zero
    sfence.vma
    la t0, failed
    csrw mtvec, t0
    li t0, 0x600
    csrs mstatus, t0
#ifdef USER_ECALL
    li t0, 0x100
    csrw medeleg, t0
#endif
#if defined(SUPERVISOR) || defined(USER_ECALL)
    li t0, -1
    csrw pmpaddr0, t0
    li t0, 0x1f
    csrw pmpcfg0, t0
    li t0, 0x1800
    csrc mstatus, t0
    li t0, 0x800
    csrs mstatus, t0
    la t0, vector_start
    csrw mepc, t0
    mret
vector_start:
#endif
#ifdef USER_ECALL
    la t0, user_trap
    csrw stvec, t0
    # User ecalls were delegated before dropping M privilege above.
    li t0, 0x100
    csrc sstatus, t0
    la t0, user_start
    csrw sepc, t0
    li s0, 8
    sret
user_start:
    vsetivli a0, 2, e64, m1, ta, ma
user_loop:
    ecall
    j user_loop
.balign 4
user_trap:
    csrr t0, scause
    li t1, 8
    bne t0, t1, failed
#else
    vsetivli a0, 2, e64, m1, ta, ma
    li s0, 8
#endif
discard:
    li a5, 0x600
    csrs sstatus, a5
    nop
    vsetvli a5, zero, e8, m8, ta, ma
    li a5, -1
    slli a5, a5, 63
    vmv.v.i v0, -1
#ifdef SERIALIZE_MOVES
    csrr zero, vl
#endif
    vmv.v.i v8, -1
#ifdef SERIALIZE_MOVES
    csrr zero, vl
#endif
    vmv.v.i v16, -1
#ifdef SERIALIZE_MOVES
    csrr zero, vl
#endif
    vmv.v.i v24, -1
#ifdef SERIALIZE_MOVES
    csrr zero, vl
#endif
    vsetvl a4, zero, a5
    nop
    li a5, 0x600
    csrc sstatus, a5
    addi s0, s0, -1
#ifdef USER_ECALL
    beqz s0, check_result
    li t0, 0x600
    csrs sstatus, t0
    csrr t0, sepc
    addi t0, t0, 4
    csrw sepc, t0
    sret
check_result:
#else
    bnez s0, discard
#endif
    li t0, 0x600
    csrs sstatus, t0
    csrr t1, vl
    bnez t1, failed
    csrr t1, vtype
    li t2, 1
    slli t2, t2, 63
    bne t1, t2, failed
    # ctrl_registers adds the completion bit; the payload is the exit code.
    li t1, 0
    j finish
.balign 4
failed:
    li t1, 1
finish:
#ifdef BOARD
    li t0, 0x03010000
    fence iorw, iorw
    sw t1, 0x20(t0)
    li t1, 1
    fence iorw, iorw
    sw t1, 0x30(t0)
    fence iorw, iorw
#else
    li t0, 0xd0000000
    sd t1, 0(t0)
#endif
1:  j 1b
