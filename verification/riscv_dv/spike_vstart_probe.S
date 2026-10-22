.section .text.init
.globl _start
_start:
    la t0, trap
    csrw mtvec, t0
    li t0, 0x600
    csrs mstatus, t0
    li t0, 2
    vsetvli zero, t0, e32, m1, ta, ma
    vmv.v.i v2, 1
    vmv.v.i v4, 1
    li t0, 1
    csrw vstart, t0
    vwadd.vv v8, v2, v4
    csrr t0, vstart
    bnez t0, fail
    li t0, 1
    j exit
trap:
fail:
    li t0, 3
exit:
    la t1, tohost
    sd t0, 0(t1)
1:  j 1b

.section .tohost,"aw",@progbits
.align 6
.globl tohost
tohost:
    .dword 0
.globl fromhost
fromhost:
    .dword 0
