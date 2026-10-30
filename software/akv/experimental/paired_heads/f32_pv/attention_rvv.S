// Exactly two real heads of one query; caller owns and validates the context.
    .text
    .option push
    .option norvc
    .p2align 2
    .globl akv_experimental_pv_f32_pair
    .type akv_experimental_pv_f32_pair,@function

// a0=F32 score, a1=F32 numerators, a2=F32 old scales, a3=T, a4=D.
// Score stride256B; output stride4*D bytes; scale stride4B.
// v0..3/v4..7: F32 accumulators; v8..9: F16 V; v12..15: widened V.
akv_experimental_pv_f32_pair:
    mv              t5, a4
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    slli            a4, t5, 2
    add             a4, t1, a4
    vsetvli         zero, t5, e32, m4, ta, ma
    vle32.v         v0, (t1)
    vle32.v         v4, (a4)
    flw             ft0, 0(t2)
    vfmul.vf        v0, v0, ft0
    flw             ft1, 4(t2)
    vfmul.vf        v4, v4, ft1
    li              t4, 0
.Lf32_pair_token:
    flw             ft0, 0(t0)
    flw             ft1, 256(t0)
    vsetvli         zero, t5, e16, m2, ta, ma
    slli            a0, t4, 2
    ori             a0, a0, 2
    li              a1, 64
    beq             t5, a1, .Lf32_pair_d64
    li              a1, 96
    beq             t5, a1, .Lf32_pair_d96
    .word           0x0205345b  // vakvload.d128 v8:v9, V selector(a0)
    j               .Lf32_pair_loaded
.Lf32_pair_d96:
    .word           0x0405345b  // vakvload.d96 v8:v9, V selector(a0)
    j               .Lf32_pair_loaded
.Lf32_pair_d64:
    .word           0x0005345b  // vakvload.d64 v8, V selector(a0)
.Lf32_pair_loaded:
    vfwcvt.f.f.v    v12, v8
    vsetvli         zero, t5, e32, m4, ta, ma
    vfmacc.vf       v0, ft0, v12
    vfmacc.vf       v4, ft1, v12
    addi            t0, t0, 4
    addi            t4, t4, 1
    bltu            t4, t3, .Lf32_pair_token
    vse32.v         v0, (t1)
    vse32.v         v4, (a4)
    ret
    .size akv_experimental_pv_f32_pair, .-akv_experimental_pv_f32_pair
    .option pop
    .section .note.GNU-stack,"",@progbits
