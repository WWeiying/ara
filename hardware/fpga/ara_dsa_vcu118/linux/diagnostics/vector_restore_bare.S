# Four back-to-back Linux-style m8 loads, no MMU or syscall dependency.
.section .text.init
.globl _start
_start:
    csrw mie, zero
    csrw satp, zero
    la t0, trap
    csrw mtvec, t0
    li t0, 0x600
    csrs mstatus, t0
#ifdef SV39
    li t0, -1
    csrw pmpaddr0, t0
    li t0, 0x1f
    csrw pmpcfg0, t0
    la t0, root_table
    srli t0, t0, 12
    li t1, 8
    slli t1, t1, 60
    or t0, t0, t1
    csrw satp, t0
    sfence.vma
    li t0, 0x1800
    csrc mstatus, t0
    li t0, 0x800
    csrs mstatus, t0
    la t0, vector_start
    csrw mepc, t0
    mret
vector_start:
#endif
    li s0, 0x03010000
    li t0, 0x100
    sw t0, 0x1c(s0)
    vsetvli a3, zero, e8, m8, ta, ma
    li t0, 1024
    bne a3, t0, failed
    la a4, source
load0:
    vle8.v v0, (a4)
#ifdef DRAIN
    csrr zero, vl
#endif
    add a4, a4, a3
#ifndef TIGHT
    li t0, 0x101
    sw t0, 0x1c(s0)
#endif
load8:
    vle8.v v8, (a4)
#ifdef DRAIN
    csrr zero, vl
#endif
    add a4, a4, a3
#ifndef TIGHT
    li t0, 0x102
    sw t0, 0x1c(s0)
#endif
load16:
    vle8.v v16, (a4)
#ifdef DRAIN
    csrr zero, vl
#endif
    add a4, a4, a3
#ifndef TIGHT
    li t0, 0x103
    sw t0, 0x1c(s0)
#endif
load24:
    vle8.v v24, (a4)
    csrr zero, vl
    li t0, 0x110
    sw t0, 0x1c(s0)
    la a4, destination
    vse8.v v0, (a4)
    add a4, a4, a3
    vse8.v v8, (a4)
    add a4, a4, a3
    vse8.v v16, (a4)
    add a4, a4, a3
    vse8.v v24, (a4)
    csrr zero, vl
    fence iorw, iorw
    li t0, 0x120
    sw t0, 0x1c(s0)
    la t0, destination
    li t1, 0
    li t4, 4096
compare:
    lbu t2, 0(t0)
    xori t3, t1, 0xa5
    andi t3, t3, 255
    bne t2, t3, failed
    addi t0, t0, 1
    addi t1, t1, 1
    bne t1, t4, compare
    li t1, 0
    j finish
failed:
    li t1, 1
    j finish
.balign 4
trap:
    csrr t1, mcause
    li t0, 0x80000000
    or t1, t1, t0
finish:
    li s0, 0x03010000
    sw t1, 0x20(s0)
    li t0, 1
    fence iorw, iorw
    sw t0, 0x30(s0)
park:
    j park
.section .data
.balign 4096
#ifdef CROSS_PAGE
    # Third 1024-byte load begins at page offset 0xfc0.
    .zero 0x7c0
#endif
source:
    .set byte_index, 0
    .rept 4096
    .byte (byte_index ^ 0xa5) & 255
    .set byte_index, byte_index + 1
    .endr
.balign 4096
destination:
    .zero 4096
#ifdef SV39
.balign 4096
root_table:
    # Identity-map MMIO and DDR as supervisor 1 GiB leaves, A/D set.
    .dword 0xcf
    .dword 0
    .dword 0x200000cf
    .zero 4072
#endif
