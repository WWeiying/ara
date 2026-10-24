// Experimental two-real-head helpers. Caller validates shape and AKV ownership.
    .text
    .p2align 2
    .globl akv_experimental_qk_f16_pair_panel4
    .type akv_experimental_qk_f16_pair_panel4,@function

// a0=query, a1=score, a2=tokens, a3=query byte stride, a4=D.
// FP32 accumulators v0:v1/v2:v3; four F16 columns v8-v11.
    .macro AKV_PAIR_COLUMN reg
    flh             ft0, 0(a4)
    flh             ft1, 0(a5)
    vfwmacc.vf      v0, ft0, \reg
    vfwmacc.vf      v2, ft1, \reg
    addi            a4, a4, 2
    addi            a5, a5, 2
    .endm

akv_experimental_qk_f16_pair_panel4:
    mv              t5, a4
    mv              a4, a0
    add             a5, a0, a3
    mv              t0, a1
    mv              t1, a2
    vsetvli         zero, t1, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vmv.v.i         v2, 0
    vsetvli         zero, t1, e16, m1, ta, ma
    li              t2, 0
.Lpair_qk_panel:
    mv              a0, t2
    .word           0x0205745b  // vakv2kpanel4 v8-v11, dimension(a0)
    AKV_PAIR_COLUMN v8
    AKV_PAIR_COLUMN v9
    AKV_PAIR_COLUMN v10
    AKV_PAIR_COLUMN v11
    addi            t2, t2, 4
    bltu            t2, t5, .Lpair_qk_panel
    vsetvli         zero, t1, e32, m2, ta, ma
    vse32.v         v0, (t0)
    addi            t0, t0, 256
    vse32.v         v2, (t0)
    ret
    .size akv_experimental_qk_f16_pair_panel4, .-akv_experimental_qk_f16_pair_panel4
    .purgem AKV_PAIR_COLUMN

    .p2align 2
    .globl akv_experimental_pv_f16_pair
    .type akv_experimental_pv_f16_pair,@function

// a0=F32 score, a1=F16 accumulator, a2=F32 old scales, a3=tokens, a4=D.
// Score rows stride256B; accumulator rows stride512B, including D64/D96.
akv_experimental_pv_f16_pair:
    mv              t5, a4
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    addi            a4, t1, 512
    vsetvli         zero, t5, e16, m2, ta, ma
    vle16.v         v0, (t1)
    vle16.v         v2, (a4)
    flw             ft0, 0(t2)
    fcvt.h.s        ft0, ft0
    vfmul.vf        v0, v0, ft0
    flw             ft1, 4(t2)
    fcvt.h.s        ft1, ft1
    vfmul.vf        v2, v2, ft1
    li              t4, 0
.Lpair_pv_token:
    flw             ft0, 0(t0)
    fcvt.h.s        ft0, ft0
    flw             ft1, 256(t0)
    fcvt.h.s        ft1, ft1
    slli            a0, t4, 2
    ori             a0, a0, 2
    li              a1, 64
    beq             t5, a1, .Lpair_pv_d64
    li              a1, 96
    beq             t5, a1, .Lpair_pv_d96
    .word           0x0205345b  // vakvload.d128 v8:v9, V selector(a0)
    j               .Lpair_pv_loaded
.Lpair_pv_d96:
    .word           0x0405345b  // vakvload.d96 v8:v9, V selector(a0)
    j               .Lpair_pv_loaded
.Lpair_pv_d64:
    .word           0x0005345b  // vakvload.d64 v8, V selector(a0)
.Lpair_pv_loaded:
    vfmacc.vf       v0, ft0, v8
    vfmacc.vf       v2, ft1, v8
    addi            t0, t0, 4
    addi            t4, t4, 1
    bltu            t4, t3, .Lpair_pv_token
    vse16.v         v0, (t1)
    vse16.v         v2, (a4)
    ret
    .size akv_experimental_pv_f16_pair, .-akv_experimental_pv_f16_pair

    .section .note.GNU-stack,"",@progbits
