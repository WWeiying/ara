/* SPDX-License-Identifier: Apache-2.0
 * Scalar-only variant of the package's smoke startup. No simulation MMIO.
 */
.section .text.start,"ax",@progbits
.globl _start
_start:
    csrw mie, zero
    csrw satp, zero
    sfence.vma
    fence iorw, iorw
    fence.i
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, __stack_top
    csrw mscratch, sp
    la t0, host_trap
    csrw mtvec, t0
    /* External AXI writes are not coherent with the private D-cache. */
    csrw 0x7c1, zero
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sd zero, 0(t0)
    addi t0, t0, 8
    j 1b
2:  call main
3:  wfi
    j 3b
.balign 4
host_trap:
    csrrw sp, mscratch, sp
    csrr a0, mcause
    csrr a1, mepc
    csrr a2, mtval
    call host_report_trap
    j 3b
