    .section .text.init,"ax",@progbits
    .globl _start
_start:
    la sp, __stack_top
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la t0, trap_entry
    csrw mtvec, t0
    li t0, ((3 << 13) | (3 << 9))
    csrs mstatus, t0
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sb zero, 0(t0)
    addi t0, t0, 1
    j 1b
2:  call probe_main
3:  wfi
    j 3b
    .balign 4
trap_entry:
    csrr a0, mcause
    csrr a1, mepc
    csrr a2, mtval
    call probe_trap
    j 3b
