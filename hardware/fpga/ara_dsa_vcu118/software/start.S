/* SPDX-License-Identifier: Apache-2.0 */
.section .text.start,"ax",@progbits
.globl _start
_start:
    csrw mie, zero
    csrw satp, zero
    sfence.vma
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, __stack_top
    la t0, trap
    csrw mtvec, t0
    li t0, 0x6600
    csrs mstatus, t0
    csrw fcsr, zero
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sd zero, 0(t0)
    addi t0, t0, 8
    j 1b
2:  fence.i
    call main
3:  wfi
    j 3b
.balign 4
trap:
    csrr a0, mcause
    csrr a1, mepc
    csrr a2, mtval
    call report_trap
    j 3b
