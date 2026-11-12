// SPDX-License-Identifier: Apache-2.0
    .text
    .option push
    .option norelax
    .globl _start
    .type _start,@function
_start:
    la gp, __global_pointer$
    andi sp, sp, -16
    call smoke_main
1:  j 1b
    .size _start, .-_start
    .option pop

    .option push
    .option arch,+f,+v
    .globl smoke_checked_execute
    .type smoke_checked_execute,@function
smoke_checked_execute:
    addi sp, sp, -32
    sd ra, 0(sp)
    sd s0, 8(sp)
    mv s0, a3
    li t0, 0x15
    csrw fcsr, t0
    li t0, 5
    csrw vcsr, t0
    csrw vstart, a2
    call ara_resident_linux_execute
    sd a0, 0(s0)
    frcsr t0
    sd t0, 8(s0)
    csrr t0, vcsr
    sd t0, 16(s0)
    csrr t0, vstart
    sd t0, 24(s0)
    // Harness cleanup happens only after recording the rejected nonzero state.
    csrwi vstart, 0
    csrwi fcsr, 0
    csrwi vcsr, 0
    ld ra, 0(sp)
    ld s0, 8(sp)
    addi sp, sp, 32
    ret
    .size smoke_checked_execute, .-smoke_checked_execute
    .option pop
    .section .note.GNU-stack,"",@progbits
