    .section .text.init
    .globl _start
_start:
    la sp, compute_stack_top
    la t0, trap
    csrw mtvec,t0
    csrwi medeleg,0
    csrwi mideleg,0
    li t0,-1
    csrw pmpaddr0,t0
    li t0,0x1f
    csrw pmpcfg0,t0
    la t0,root_page
    li t1,512
1:  sd zero,0(t0)
    addi t0,t0,8
    addi t1,t1,-1
    bnez t1,1b
    la t0,root_page
    li t1,0x200000ef
    sd t1,16(t0)
    li t2,2048
    add t2,t0,t2
    sd t1,0(t2)
    li t1,0x300000ef
    sd t1,24(t0)
    srli t0,t0,12
    li t1,0x8000000000000000
    or t0,t0,t1
    csrw satp,t0
    sfence.vma
    li t0,0x6e00
    csrw mstatus,t0
    la t0,supervisor_main
    csrw mepc,t0
    mret
supervisor_main:
    csrwi fcsr,0
    csrwi vstart,0
    call main
    li t0,0xd0000000
    sd a0,0(t0)
2:  j 2b
    .balign 4
trap:
    csrr a0,mcause
    csrr a1,mtval
    csrr a2,mepc
    call trap_report
    li a0,1
    li t0,0xd0000000
    sd a0,0(t0)
3:  j 3b
    .section .bss
    .balign 4096
root_page:
    .space 4096
    .balign 16
    .space 65536
compute_stack_top:
    .section .note.GNU-stack,"",@progbits
