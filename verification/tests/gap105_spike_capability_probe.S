/* ISA capability probe only, not the QBS app or a numerical oracle. */
.section .text
.globl _start
_start:
    li t0, 0x6600
    csrs mstatus, t0
    la t0, probe_trap
    csrw mtvec, t0
    li a3, 0
    csrr t0, vlenb
    li t1, 128
    bne t0, t1, probe_fail
.globl probe_info
probe_info:
    .word 0x0005155b
    li t0, 1
    vsetvli zero, t0, e32, m1, tu, mu
    csrwi vstart, 0
.globl probe_exec
probe_exec:
    .word 0x0eb5045b
    li t0, 2
    bne a3, t0, probe_fail
    la t1, probe_ledger
    ld t2, 0(t1)
    bne t2, t0, probe_fail
    ld t2, 24(t1)
    bne t2, t0, probe_fail
    li t0, 0x0005155b
    ld t2, 8(t1)
    bne t2, t0, probe_fail
    li t0, 0x0eb5045b
    ld t2, 32(t1)
    bne t2, t0, probe_fail
    li t0, 1
    j probe_exit
probe_fail:
    li t0, 3
probe_exit:
    la t1, tohost
    sd t0, 0(t1)
1:  j 1b
.balign 4
probe_trap:
    la t0, probe_ledger
    li t1, 24
    mul t1, a3, t1
    add t0, t0, t1
    csrr t1, mcause
    sd t1, 0(t0)
    csrr t1, mtval
    sd t1, 8(t0)
    csrr t1, mepc
    sd t1, 16(t0)
    addi t1, t1, 4
    csrw mepc, t1
    addi a3, a3, 1
    mret
.section .data
.balign 64
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
.globl probe_ledger
probe_ledger: .zero 48
