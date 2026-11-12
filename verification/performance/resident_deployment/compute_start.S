    .section .text.init
    .globl _start
_start:
    la sp, compute_stack_top
    li t0, 0x6600
    csrs mstatus,t0
    csrwi fcsr,0
    csrwi vstart,0
    la t0, trap
    csrw mtvec,t0
    call main
    li t0,0xd0000000
    sd a0,0(t0)
1:  j 1b
    .balign 4
trap:
    li a0,1
    li t0,0xd0000000
    sd a0,0(t0)
2:  j 2b
    .section .bss
    .balign 16
    .space 65536
compute_stack_top:
    .section .note.GNU-stack,"",@progbits
