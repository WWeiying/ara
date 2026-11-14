// Derived from resident_deployment/compute_start.S; bare metal, no Linux entry.
    .section .text.init
    .globl _start
_start:
    la sp, stack_top
    la t0, trap
    csrw mtvec, t0
    li t0, 0x6600
    csrs mstatus, t0
    csrwi fcsr, 0
    csrwi vstart, 0
    call main
    li t0, 0xd0000000
    sd a0, 0(t0)
1:  j 1b
    .balign 4
trap:
    csrr a0, mcause
    csrr a1, mepc
    csrr a2, mtval
    call trap_report
    li a0, 1
    li t0, 0xd0000000
    sd a0, 0(t0)
2:  j 2b
    .section .bss
    .balign 16
    .space 65536
stack_top:
    .section .note.GNU-stack,"",@progbits
