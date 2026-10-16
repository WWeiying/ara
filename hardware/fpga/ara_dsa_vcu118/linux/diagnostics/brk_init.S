.section .text
.globl _start
_start:
    li a0, 1
    la a1, before
    la t0, before_end
    sub a2, t0, a1
    li a7, 64
    ecall

    li a0, 0
    li a7, 214
    ecall
    li t0, 4096
    add a0, a0, t0
    li a7, 214
    ecall

    li a0, 1
    la a1, after
    la t0, after_end
    sub a2, t0, a1
    li a7, 64
    ecall
1:
    j 1b

.section .rodata
before:
    .ascii "ARA_BRK_BEFORE\n"
before_end:
after:
    .ascii "ARA_BRK_AFTER\n"
after_end:
