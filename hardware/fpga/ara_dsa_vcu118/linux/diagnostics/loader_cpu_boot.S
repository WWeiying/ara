/* Simulation bootstrap only. The U-mode code is the captured, unmodified ELF. */
.section .text
.globl _start
_start:
    csrw mie, zero
    la t0, failed
    csrw mtvec, t0
    li t0, ROOT_SATP
    csrw satp, t0
    sfence.vma
    li sp, USER_SP
    li a0, 0
    li a1, 0
    li a2, 0
    li a3, 0
    li t0, 0x6600
    csrw mstatus, t0
    li t0, USER_ENTRY
    csrw mepc, t0
    mret
failed:
    j failed
