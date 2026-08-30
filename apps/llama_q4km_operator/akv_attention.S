// Fixed-register D128/GQA6 Attention kernel for the AKV v1 contract.
// Q/K/V movement uses AKV commands; all arithmetic and architectural results
// use ordinary RVV instructions and the existing Ara dependency machinery.

    .section .text.attention_akv_group_asm,"ax",@progbits
    .align  2
    .globl  attention_akv_group_asm
    .type   attention_akv_group_asm,@function

// Approximate exp(x) for six FP32 lanes. The polynomial and evaluation order
// match vector_expf_f32m1() in main.c. The source and destination are the same
// register; v14/v16/v20/v22/v29-v31 are scratch after the dot products.
    .macro AKV_EXP_F32M1 vd
    vfmv.v.f       v14, ft2
    vmv.v.v        v16, v14
    vfmacc.vf      v16, ft3, \vd
    vfsub.vv       v20, v16, v14
    vmv.v.v        v22, \vd
    vfnmsac.vf     v22, ft4, v20
    vfnmsac.vf     v22, ft5, v20
    vsll.vi        v29, v16, 23
    vadd.vx        v29, v29, a4
    vfmul.vv       v30, v22, v22
    vfmv.v.f       v31, ft7
    vfmacc.vf      v31, fa0, v22
    vfmv.v.f       v14, fa1
    vfmacc.vf      v14, fa2, v22
    vfmacc.vv      v31, v14, v30
    vfmul.vf       v14, v22, ft6
    vfmacc.vv      v14, v31, v30
    vmv.v.v        \vd, v29
    vfmacc.vv      \vd, v14, v29
    .endm

// Load one resident Q row, form a D128 FP16 dot product with resident K,
// reduce entirely in the vector domain, and insert the scalar vector result
// into scores[index].
    .macro AKV_DOT_Q selector, index, pack_vl
    li              a0, \selector
    .word           0x0205385b       // vakvload.d128 v16:v17, selector(a0)
    li              a5, 64
    vsetvli         zero, a5, e32, m2, ta, ma
    vmv.v.i         v20, 0
    vsetvli         zero, a5, e16, m1, ta, ma
    vfwmacc.vv      v20, v14, v16
    vfwmacc.vv      v20, v15, v17
    vsetivli        zero, 1, e32, m1, ta, ma
    vmv.s.x         v22, zero
    vsetvli         zero, a5, e32, m2, ta, ma
    vfredusum.vs    v22, v20, v22
    vsetivli        zero, \pack_vl, e32, m1, tu, ma
    vslideup.vi     v23, v22, \index
    .endm

// Update one FP16m2 online-softmax output vector. v30 contains the six
// old-state factors, v16 the six new-score factors, and v18:v19 the V row.
// Ara's general VRGATHER path scans a complete source group even for a scalar
// splat, so extracting two factors and using vector-scalar arithmetic is both
// semantically exact and substantially cheaper for this six-head GQA shape.
    .macro AKV_UPDATE_OUTPUT vd, index
    vsetivli        zero, 1, e16, mf2, ta, ma
    vslidedown.vi   v20, v30, \index
    vfmv.f.s        fa4, v20
    vslidedown.vi   v22, v16, \index
    vfmv.f.s        fa5, v22
    li              a5, 128
    vsetvli         zero, a5, e16, m2, ta, ma
    vfmul.vf        \vd, \vd, fa4
    vfmacc.vf       \vd, fa5, v18
    .endm

// Convert one FP16m2 output to FP32m4, apply its normalization scalar, and
// store 128 elements. v25 retains all six inverse sums throughout.
    .macro AKV_STORE_OUTPUT vs, index
    vsetivli        zero, 1, e32, m1, ta, ma
    vslidedown.vi   v26, v25, \index
    vfmv.f.s        ft1, v26
    li              a5, 128
    vsetvli         zero, a5, e16, m2, ta, ma
    vfwcvt.f.f.v    v20, \vs
    vsetvli         zero, a5, e32, m4, ta, ma
    vfmul.vf        v20, v20, ft1
    vse32.v         v20, (t2)
    addi            t2, t2, 512
    .endm

// a0: AKV descriptor, a1: FP16 mask for the active prefix,
// a2: six contiguous D128 FP32 output rows, fa0: attention scale.
attention_akv_group_asm:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    lhu             t3, 6(t0)       // descriptor.kv_length
    fmv.s           ft0, fa0

    la              a5, .Lakv_exp_constants
    flw             ft2, 0(a5)      // r
    flw             ft3, 4(a5)      // log2(e)
    flw             ft4, 8(a5)      // ln(2), high
    flw             ft5, 12(a5)     // ln(2), low
    flw             ft6, 16(a5)     // c1
    flw             ft7, 20(a5)     // c2
    flw             fa0, 24(a5)     // c3
    flw             fa1, 28(a5)     // c4
    flw             fa2, 32(a5)     // c5
    flw             fa3, 36(a5)     // 1.0
    li              a4, 0x3f800000

    mv              a0, t0
    li              a1, 0
    fence           rw, rw
    .word           0x00b5205b       // vakvfull descriptor(a0), tile_start(a1)

    li              t4, 0
.Lakv_sequence_loop:
    beqz            t4, .Lakv_tile_ready
    andi            t5, t4, 7
    bnez            t5, .Lakv_tile_ready
    mv              a0, t4
    .word           0x02a0205b       // vakvrefill tile_start(a0)

.Lakv_tile_ready:
    andi            a0, t4, 7
    slli            a0, a0, 2
    ori             a0, a0, 1
    .word           0x0205375b       // vakvload.d128 v14:v15, K selector(a0)

    vsetivli        zero, 6, e32, m1, ta, ma
    vmv.v.i         v23, 0
    AKV_DOT_Q        0, 0, 1
    AKV_DOT_Q        4, 1, 2
    AKV_DOT_Q        8, 2, 3
    AKV_DOT_Q        12, 3, 4
    AKV_DOT_Q        16, 4, 5
    AKV_DOT_Q        20, 5, 6

    vsetivli        zero, 6, e32, m1, ta, ma
    vfmul.vf        v23, v23, ft0
    flh             ft1, 0(t1)
    fcvt.s.h        ft1, ft1
    vfadd.vf        v23, v23, ft1

    andi            a0, t4, 7
    slli            a0, a0, 2
    ori             a0, a0, 2
    .word           0x0205395b       // vakvload.d128 v18:v19, V selector(a0)

    bnez            t4, .Lakv_online_update
    vmv.v.v         v24, v23
    vfmv.v.f        v25, fa3
    vmv2r.v         v2, v18
    vmv2r.v         v4, v18
    vmv2r.v         v6, v18
    vmv2r.v         v8, v18
    vmv2r.v         v10, v18
    vmv2r.v         v12, v18
    j               .Lakv_sequence_done

.Lakv_online_update:
    vfmax.vv        v26, v24, v23
    vfsub.vv        v27, v24, v26
    vfsub.vv        v28, v23, v26
    AKV_EXP_F32M1   v27
    AKV_EXP_F32M1   v28
    vfmul.vv        v25, v25, v27
    vfadd.vv        v25, v25, v28
    vmv.v.v         v24, v26

    vsetivli        zero, 6, e16, mf2, ta, ma
    vfncvt.f.f.w    v30, v27
    vfncvt.f.f.w    v16, v28
    li              a5, 128
    vsetvli         zero, a5, e16, m2, ta, ma
    AKV_UPDATE_OUTPUT v2, 0
    AKV_UPDATE_OUTPUT v4, 1
    AKV_UPDATE_OUTPUT v6, 2
    AKV_UPDATE_OUTPUT v8, 3
    AKV_UPDATE_OUTPUT v10, 4
    AKV_UPDATE_OUTPUT v12, 5

.Lakv_sequence_done:
    addi            t4, t4, 1
    addi            t1, t1, 2
    bltu            t4, t3, .Lakv_sequence_loop

#ifndef SPIKE
    la              t6, hw_cnt_en_reg
    li              a5, 0x301
    sd              a5, 0(t6)
    fence           ow, ow
#endif

    vsetivli        zero, 6, e32, m1, ta, ma
    vfrdiv.vf       v25, v25, fa3
    AKV_STORE_OUTPUT v2, 0
    AKV_STORE_OUTPUT v4, 1
    AKV_STORE_OUTPUT v6, 2
    AKV_STORE_OUTPUT v8, 3
    AKV_STORE_OUTPUT v10, 4
    AKV_STORE_OUTPUT v12, 5

    .word           0x0000505b       // vakvrelease
    ret

    .size attention_akv_group_asm, .-attention_akv_group_asm

    .section .rodata.akv_exp,"a",@progbits
    .align  2
.Lakv_exp_constants:
    .float  0x1.8p23
    .float  0x1.715476p+0
    .float  0x1.62e4p-1
    .float  0x1.7f7d1cp-20
    .float  0x1.ffffecp-1
    .float  0x1.fffdb6p-2
    .float  0x1.555e66p-3
    .float  0x1.573e2ep-5
    .float  0x1.0e4020p-7
    .float  1.0
