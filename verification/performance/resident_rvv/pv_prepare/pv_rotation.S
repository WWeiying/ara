// Diagnostic wrapper: prepare once, capture its source, then run the unchanged
// rotated RVV body. Only the nested preparation interval is a cost measurement.
    .text
    .p2align 2
    .globl __wrap_akv_experimental_pv_f16_pair
    .type __wrap_akv_experimental_pv_f16_pair,@function
__wrap_akv_experimental_pv_f16_pair:
    la t0, resident_pv_rotation_selected
    lw t0, 0(t0)
    beqz t0, resident_pv_rotation_body
    addi sp, sp, -80
    sd ra, 0(sp)
    sd a0, 8(sp)
    sd a1, 16(sp)
    sd a2, 24(sp)
    sd a3, 32(sp)
    sd a4, 40(sp)
    call resident_prepare_before
    sd a0, 48(sp)
    ld a0, 8(sp)
    ld a1, 16(sp)
    ld a2, 24(sp)
    ld a3, 32(sp)
    ld a4, 40(sp)
    li a5, 2
    rdcycle t0
    sd t0, 56(sp)
    call resident_pv_prepare
    rdcycle t1
    ld t0, 56(sp)
    sub t1, t1, t0
    sd t1, 64(sp)
    li t0, 384
    vsetvli zero, t0, e16, m8, ta, ma
    ld t0, 48(sp)
    vse16.v v8, (t0)
    fence rw, rw
    rdcycle a1
    ld t0, 56(sp)
    sub a1, a1, t0
    ld a0, 64(sp)
    frcsr a2
    call resident_prepare_after
    ld ra, 0(sp)
    ld a0, 8(sp)
    ld a1, 16(sp)
    ld a2, 24(sp)
    ld a3, 32(sp)
    ld a4, 40(sp)
    addi sp, sp, 80
    j resident_pv_rotation_body
    .size __wrap_akv_experimental_pv_f16_pair, .-__wrap_akv_experimental_pv_f16_pair
    .section .note.GNU-stack,"",@progbits
