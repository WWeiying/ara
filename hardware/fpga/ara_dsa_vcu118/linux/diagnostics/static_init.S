.section .text
.globl _start
_start:
    li a0, 1
    la a1, marker
    la t0, marker_end
    sub a2, t0, a1
    li a7, 64
    ecall
1:
    j 1b

.section .rodata
marker:
    .ascii "Ara DSA VCU118 Linux init reached\n"
    .ascii "Linux console, DDR and RVV handoff are alive\n"
    .ascii "ARA_STATIC_INIT_REACHED\n"
marker_end:
