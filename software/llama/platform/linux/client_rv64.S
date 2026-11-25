// SPDX-License-Identifier: Apache-2.0
    .text
    .option push
    .option arch,+f,+v
    // Both descriptors place returned fflags at byte 28.
    .macro resident_entry name, scalar
    .p2align 2
    .globl \name
    .type \name,@function
\name:
    csrr t0, vstart
    bnez t0, .Lbad_vstart\@
    addi sp, sp, -48
    sd ra, 0(sp)
    frcsr t0
    sd t0, 8(sp)
    csrr t0, vcsr
    sd t0, 16(sp)
    sd a1, 24(sp)
    call \scalar
    ld t0, 8(sp)
    bnez a0, .Lrestore\@
    ld t1, 24(sp)
    lwu t1, 28(t1)
    andi t1, t1, 31
    or t0, t0, t1
.Lrestore\@:
    csrw fcsr, t0
    ld t0, 16(sp)
    csrw vcsr, t0
    csrwi vstart, 0
    ld ra, 0(sp)
    addi sp, sp, 48
    ret
.Lbad_vstart\@:
    li a0, -34
    ret
    .size \name, .-\name
    .endm
    resident_entry ara_resident_linux_execute, ara_resident_linux_execute_scalar
    resident_entry ara_resident_linux_execute_batch, ara_resident_linux_execute_batch_scalar
    .option pop
    .section .note.GNU-stack,"",@progbits
