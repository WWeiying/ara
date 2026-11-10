    .section .text.init,"ax",@progbits
    .balign 4
    .global _start
_start:
    la sp, probe_stack_end
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la t0, probe_trap
    csrw mtvec, t0
    li t0, 0x6600
    csrs mstatus, t0
    csrwi fcsr, 0
    csrwi vstart, 0
    call probe_main
    slli a0, a0, 1
    ori a0, a0, 1
    j probe_exit
    .balign 4
probe_trap:
    li a0, 3
probe_exit:
    la t0, tohost
    sd a0, 0(t0)
1:  j 1b
    .section .bss
    .balign 16
probe_stack:
    .skip 32768
probe_stack_end:
    .section .tohost,"aw",@progbits
    .balign 64
    .global tohost
tohost: .dword 0
    .global fromhost
fromhost: .dword 0
    .section .note.GNU-stack,"",@progbits
