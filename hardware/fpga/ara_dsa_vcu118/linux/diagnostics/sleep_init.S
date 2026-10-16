.section .text
.globl _start
_start:
    la a0, devtmpfs
    la a1, devdir
    la a2, devtmpfs
    li a3, 0
    li a4, 0
    li a7, 40
    ecall

    li a0, -100
    la a1, kmsg_path
    li a2, 1
    li a3, 0
    li a7, 56
    ecall
    bltz a0, failed
    mv s0, a0

    mv a0, s0
    la a1, before
    la t0, before_end
    sub a2, t0, a1
    li a7, 64
    ecall

    la a0, delay
    li a1, 0
    li a7, 101
    ecall
    mv s1, a0

    mv a0, s0
    la a1, after
    la t0, after_end
    sub a2, t0, a1
    li a7, 64
    ecall

    bltz s1, failed
1:
    j 1b

failed:
    li a7, 93
    ecall

.section .rodata
devtmpfs:
    .asciz "devtmpfs"
devdir:
    .asciz "/dev"
kmsg_path:
    .asciz "/dev/kmsg"
before:
    .ascii "<0>ARA_SLEEP_BEFORE\n"
before_end:
after:
    .ascii "<0>ARA_SLEEP_AFTER\n"
after_end:

.section .data
.balign 8
delay:
    .dword 1
    .dword 0
