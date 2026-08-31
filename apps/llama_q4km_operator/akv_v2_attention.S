// AKV-v2 token-axis helpers for the real Qwen D128/GQA6 Attention benchmark.
// The helpers keep all arithmetic in standard RVV. Custom instructions only
// expose one K column or one V row from the resident row-major context.

    .section .text.akv_v2_attention,"ax",@progbits
    .align  2

    .globl  akv_v2_compute_scores_f16_d128_gqa6
    .type   akv_v2_compute_scores_f16_d128_gqa6,@function

// a0: six row-major F16 D128 Query rows
// a1: six row-major F32 score rows, each with a 64-element stride
// a2: active token count, 1..64
akv_v2_compute_scores_f16_d128_gqa6:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2

    vsetvli         zero, t2, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vmv.v.i         v2, 0
    vmv.v.i         v4, 0
    vmv.v.i         v6, 0
    vmv.v.i         v10, 0
    vmv.v.i         v12, 0

    vsetvli         zero, t2, e16, m1, ta, ma
    li              t3, 0
    li              t4, 128
.Lakv_v2_score_dimension:
    mv              a0, t3
    .word           0x0005745b  // vakv2kcol v8, dimension(a0)

    flh             ft0, 0(t0)
    flh             ft1, 256(t0)
    flh             ft2, 512(t0)
    flh             ft3, 768(t0)
    flh             ft4, 1024(t0)
    flh             ft5, 1280(t0)
    vfwmacc.vf      v0, ft0, v8
    vfwmacc.vf      v2, ft1, v8
    vfwmacc.vf      v4, ft2, v8
    vfwmacc.vf      v6, ft3, v8
    vfwmacc.vf      v10, ft4, v8
    vfwmacc.vf      v12, ft5, v8

    addi            t0, t0, 2
    addi            t3, t3, 1
    bltu            t3, t4, .Lakv_v2_score_dimension

    vsetvli         zero, t2, e32, m2, ta, ma
    vse32.v         v0, (t1)
    addi            t1, t1, 256
    vse32.v         v2, (t1)
    addi            t1, t1, 256
    vse32.v         v4, (t1)
    addi            t1, t1, 256
    vse32.v         v6, (t1)
    addi            t1, t1, 256
    vse32.v         v10, (t1)
    addi            t1, t1, 256
    vse32.v         v12, (t1)
    ret

    .size akv_v2_compute_scores_f16_d128_gqa6, \
          .-akv_v2_compute_scores_f16_d128_gqa6

    .globl  akv_v2_update_outputs_f16_d128_gqa6
    .type   akv_v2_update_outputs_f16_d128_gqa6,@function

// a0: six row-major F32 softmax-weight rows, 64-element stride
// a1: six row-major F16 D128 output accumulators
// a2: six F32 old-state scale factors
// a3: active token count, 1..64
akv_v2_update_outputs_f16_d128_gqa6:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3

    li              t4, 128
    vsetvli         zero, t4, e16, m2, ta, ma
    mv              a4, t1
    vle16.v         v0, (a4)
    addi            a4, a4, 256
    vle16.v         v2, (a4)
    addi            a4, a4, 256
    vle16.v         v4, (a4)
    addi            a4, a4, 256
    vle16.v         v6, (a4)
    addi            a4, a4, 256
    vle16.v         v10, (a4)
    addi            a4, a4, 256
    vle16.v         v12, (a4)

    flw             ft0, 0(t2)
    flw             ft1, 4(t2)
    flw             ft2, 8(t2)
    flw             ft3, 12(t2)
    flw             ft4, 16(t2)
    flw             ft5, 20(t2)
    fcvt.h.s        ft0, ft0
    fcvt.h.s        ft1, ft1
    fcvt.h.s        ft2, ft2
    fcvt.h.s        ft3, ft3
    fcvt.h.s        ft4, ft4
    fcvt.h.s        ft5, ft5
    vfmul.vf        v0, v0, ft0
    vfmul.vf        v2, v2, ft1
    vfmul.vf        v4, v4, ft2
    vfmul.vf        v6, v6, ft3
    vfmul.vf        v10, v10, ft4
    vfmul.vf        v12, v12, ft5

    li              t4, 0
.Lakv_v2_value_token:
    flw             ft0, 0(t0)
    flw             ft1, 256(t0)
    flw             ft2, 512(t0)
    flw             ft3, 768(t0)
    flw             ft4, 1024(t0)
    flw             ft5, 1280(t0)
    fcvt.h.s        ft0, ft0
    fcvt.h.s        ft1, ft1
    fcvt.h.s        ft2, ft2
    fcvt.h.s        ft3, ft3
    fcvt.h.s        ft4, ft4
    fcvt.h.s        ft5, ft5

    slli            a0, t4, 2
    ori             a0, a0, 2
    .word           0x0205375b  // vakvload.d128 v14:v15, V selector(a0)
    vfmacc.vf       v0, ft0, v14
    vfmacc.vf       v2, ft1, v14
    vfmacc.vf       v4, ft2, v14
    vfmacc.vf       v6, ft3, v14
    vfmacc.vf       v10, ft4, v14
    vfmacc.vf       v12, ft5, v14

    addi            t0, t0, 4
    addi            t4, t4, 1
    bltu            t4, t3, .Lakv_v2_value_token

    mv              a4, t1
    vse16.v         v0, (a4)
    addi            a4, a4, 256
    vse16.v         v2, (a4)
    addi            a4, a4, 256
    vse16.v         v4, (a4)
    addi            a4, a4, 256
    vse16.v         v6, (a4)
    addi            a4, a4, 256
    vse16.v         v10, (a4)
    addi            a4, a4, 256
    vse16.v         v12, (a4)
    ret

    .size akv_v2_update_outputs_f16_d128_gqa6, \
          .-akv_v2_update_outputs_f16_d128_gqa6
