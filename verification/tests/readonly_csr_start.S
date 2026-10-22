// SPDX-License-Identifier: SHL-0.51
.section .text.init
.globl _start
_start:
  li sp, 0x80200000
  .option push
  .option norelax
  la gp, __global_pointer$
  .option pop
  li t0, 0x6600
  csrs mstatus, t0
  la t0, trap_fail
  csrw mtvec, t0
  // VCS preloads file-backed segments into randomly initialized SRAM.
  la t0, __bss_start
  la t1, __bss_end
1:
  bgeu t0, t1, 2f
  sd zero, 0(t0)
  addi t0, t0, 8
  j 1b
2:
  call main
  slli a0, a0, 1
  ori a0, a0, 1
  j finish
.balign 4
.globl trap_fail
trap_fail:
  la t0, g75_trap
  csrr t1, mcause
  sd t1, 0(t0)
  csrr t1, mepc
  sd t1, 8(t0)
  csrr t1, mtval
  sd t1, 16(t0)
  li a0, 3
finish:
  la t0, tohost
  sd a0, 0(t0)
1: j 1b
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
.section .bss
.balign 8
.globl g75_trap
g75_trap: .zero 24
