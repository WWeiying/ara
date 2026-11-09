// Experimental wrapper, not runtime selection or an accepted optimization.
// a0=FP32 probability, a1=FP16 accumulator (512B/head), a2=FP32 scale,
// a3=T (1..64), a4=D (64/96/128). The inherited caller supplies H2.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl __wrap_akv_experimental_pv_f16_pair
    .type __wrap_akv_experimental_pv_f16_pair,@function
__wrap_akv_experimental_pv_f16_pair:
    la              t0, resident_pv_rotation_selected
    lw              t0, 0(t0)
    bnez            t0, .Lresident_pv
    tail            resident_pv_rotation_body
.Lresident_pv:
    addi            sp, sp, -32
    sd              ra, 0(sp)
    sd              a1, 8(sp)
    sd              a4, 16(sp)
    li              a5, 2
    call            resident_pv_prepare
    // prepare preserves a3/a4; scalar rs1 is now the PV control, not a pointer.
    addi            a0, a3, -1
    ori             a0, a0, 64
    li              t0, 64
    beq             a4, t0, .Lresident_issue
    li              t0, 96
    beq             a4, t0, .Lresident_d96
    ori             a0, a0, 128
    j               .Lresident_issue
.Lresident_d96:
    ori             a0, a0, 256
.Lresident_issue:
    .word           0x0485705b  // custom2/7/2, vd=v0, rs1=a0, vs2=v8
    ld              a1, 8(sp)
    ld              a4, 16(sp)
    vsetvli         zero, a4, e16, m2, ta, ma
    vse16.v         v0, (a1)
    addi            t0, a1, 512
    vse16.v         v2, (t0)
    ld              ra, 0(sp)
    addi            sp, sp, 32
    ret
    .size __wrap_akv_experimental_pv_f16_pair, .-__wrap_akv_experimental_pv_f16_pair
    .option pop
    .section .note.GNU-stack,"",@progbits
