.section .text.init
.global _start
_start:
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, __stack_top
    csrw mie, zero
    la t0, trap_entry
    csrw mtvec, t0
    li t0, 0x6600
    csrs mstatus, t0
    csrwi fcsr, 0
    csrwi vstart, 0
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sd zero, 0(t0)
    addi t0, t0, 8
    j 1b
2:  call main
    j replay_exit

.balign 4
trap_entry:
    csrr a0, mcause
    csrr a1, mepc
    csrr a2, mtval
    call replay_trap
    li a0, 127
.global replay_exit
replay_exit:
#ifdef SPIKE_REFERENCE
    slli a0, a0, 1
    ori a0, a0, 1
    la t0, tohost
#else
    // CTRL adds the valid bit; unlike HTIF it takes the raw return code.
    li t0, 0xd0000000
#endif
    fence rw, rw
    sd a0, 0(t0)
3:  j 3b
