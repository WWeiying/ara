# Hash-pinned standard-V kernel diagnostic. Reclaims three existing NOPs.
.option rvc
.option norelax
.section .text
.globl _start
_start:
restore_return:
    .space 0x12
fragment:
    ld a4, 256(a0)
    andi a4, a4, 1536
    c.beqz a4, restore_return
    lui a4, 1
    add a4, a4, a5
    ld a4, -1112(a4)
    li a3, 1536
    csrs sstatus, a3
    vsetvli a3, zero, e8, m8, ta, ma
    vle8.v v0, (a4)
    csrr zero, vl
    add a4, a4, a3
    vle8.v v8, (a4)
    csrr zero, vl
    add a4, a4, a3
    vle8.v v16, (a4)
    csrr zero, vl
    add a4, a4, a3
    vle8.v v24, (a4)
    lui a4, 1
    add a4, a4, a5
    ld a3, -1152(a4)
    ld a2, -1136(a4)
    ld a4, -1144(a4)
    vsetvl zero, a4, a2
    csrw vstart, a3
# The patch builder checks the linked binary's exact extent before writing.
