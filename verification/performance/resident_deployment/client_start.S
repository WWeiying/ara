    .section .text.init
    .globl _start
_start:
    la sp, stack_top
    li t0, 0x6600
    csrs mstatus,t0
    csrwi fcsr,0
    csrwi vstart,0
    call main
    .globl test_exit
test_exit:
    j test_exit
    .section .bss
    .balign 16
    .space 65536
stack_top:
    .section .note.GNU-stack,"",@progbits
