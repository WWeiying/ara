// AKV-v2 token-axis helpers for the D128/GQA6 Attention kernel. Arithmetic
// remains standard RVV; custom commands only expose resident K columns and V
// rows. These helpers are shared by the standalone benchmark and GGML backend.

    .section .text.akv_v2_attention,"ax",@progbits
    .align  2

    .globl  akv_v2_compute_scores_f16_d128_gqa6
    .type   akv_v2_compute_scores_f16_d128_gqa6,@function

// a0: six F16 D128 Query rows
// a1: six row-major F32 score rows, each with a 64-element stride
// a2: active token count, 1..64
// a3: Query row stride in bytes
akv_v2_compute_scores_f16_d128_gqa6:
    mv              a4, a0
    add             a5, a4, a3
    add             a6, a5, a3
    add             a7, a6, a3
    add             t5, a7, a3
    add             t6, t5, a3
    mv              t0, a1
    mv              t1, a2

    vsetvli         zero, t1, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vmv.v.i         v2, 0
    vmv.v.i         v4, 0
    vmv.v.i         v6, 0
    vmv.v.i         v10, 0
    vmv.v.i         v12, 0

    vsetvli         zero, t1, e16, m1, ta, ma
    li              t2, 0
    li              t3, 128
.Lakv_v2_score_dimension_pair:
    mv              a0, t2
    .word           0x0005745b  // vakv2kcol v8, dimension(a0)

    flh             ft0, 0(a4)
    flh             ft1, 0(a5)
    flh             ft2, 0(a6)
    flh             ft3, 0(a7)
    flh             ft4, 0(t5)
    flh             ft5, 0(t6)
    vfwmacc.vf      v0, ft0, v8
    vfwmacc.vf      v2, ft1, v8
    vfwmacc.vf      v4, ft2, v8
    vfwmacc.vf      v6, ft3, v8
    vfwmacc.vf      v10, ft4, v8
    vfwmacc.vf      v12, ft5, v8

    addi            a4, a4, 2
    addi            a5, a5, 2
    addi            a6, a6, 2
    addi            a7, a7, 2
    addi            t5, t5, 2
    addi            t6, t6, 2
    addi            t2, t2, 1

    mv              a0, t2
    .word           0x000574db  // vakv2kcol v9, dimension(a0)

    flh             ft0, 0(a4)
    flh             ft1, 0(a5)
    flh             ft2, 0(a6)
    flh             ft3, 0(a7)
    flh             ft4, 0(t5)
    flh             ft5, 0(t6)
    vfwmacc.vf      v0, ft0, v9
    vfwmacc.vf      v2, ft1, v9
    vfwmacc.vf      v4, ft2, v9
    vfwmacc.vf      v6, ft3, v9
    vfwmacc.vf      v10, ft4, v9
    vfwmacc.vf      v12, ft5, v9

    addi            a4, a4, 2
    addi            a5, a5, 2
    addi            a6, a6, 2
    addi            a7, a7, 2
    addi            t5, t5, 2
    addi            t6, t6, 2
    addi            t2, t2, 1
    bltu            t2, t3, .Lakv_v2_score_dimension_pair

    vsetvli         zero, t1, e32, m2, ta, ma
    vse32.v         v0, (t0)
    addi            t0, t0, 256
    vse32.v         v2, (t0)
    addi            t0, t0, 256
    vse32.v         v4, (t0)
    addi            t0, t0, 256
    vse32.v         v6, (t0)
    addi            t0, t0, 256
    vse32.v         v10, (t0)
    addi            t0, t0, 256
    vse32.v         v12, (t0)
    ret

    .size akv_v2_compute_scores_f16_d128_gqa6, \
          .-akv_v2_compute_scores_f16_d128_gqa6

    .globl  akv_v2_compute_scores_f16_d128_gqa6_q2
    .type   akv_v2_compute_scores_f16_d128_gqa6_q2,@function

// a0: first six-row F16 D128 Query group
// a1: second six-row F16 D128 Query group
// a2: two six-row F32 score sets; each row has a 64-element stride and the
//     second set starts after AKV_MAX_Q_ROWS rows
// a3: active token count for the later Query, 1..64. The earlier Query may
//     expose one fewer causal token; its caller consumes only that prefix.
akv_v2_compute_scores_f16_d128_gqa6_q2:
    mv              a6, a0
    mv              a7, a1
    mv              t0, a2
    mv              t1, a3

    vsetvli         zero, t1, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vmv.v.i         v2, 0
    vmv.v.i         v4, 0
    vmv.v.i         v6, 0
    vmv.v.i         v8, 0
    vmv.v.i         v10, 0
    vmv.v.i         v12, 0
    vmv.v.i         v14, 0
    vmv.v.i         v16, 0
    vmv.v.i         v18, 0
    vmv.v.i         v20, 0
    vmv.v.i         v22, 0

    vsetvli         zero, t1, e16, m1, ta, ma
    li              t2, 0
    li              t3, 128
.Lakv_v2_q2_score_dimension_pair:
    mv              a0, t2
    .word           0x00057c5b  // vakv2kcol v24, dimension(a0)

    flh             ft0, 0(a6)
    flh             ft1, 256(a6)
    flh             ft2, 512(a6)
    flh             ft3, 768(a6)
    flh             ft4, 1024(a6)
    flh             ft5, 1280(a6)
    flh             ft6, 0(a7)
    flh             ft7, 256(a7)
    flh             ft8, 512(a7)
    flh             ft9, 768(a7)
    flh             ft10, 1024(a7)
    flh             ft11, 1280(a7)
    vfwmacc.vf      v0, ft0, v24
    vfwmacc.vf      v2, ft1, v24
    vfwmacc.vf      v4, ft2, v24
    vfwmacc.vf      v6, ft3, v24
    vfwmacc.vf      v8, ft4, v24
    vfwmacc.vf      v10, ft5, v24
    vfwmacc.vf      v12, ft6, v24
    vfwmacc.vf      v14, ft7, v24
    vfwmacc.vf      v16, ft8, v24
    vfwmacc.vf      v18, ft9, v24
    vfwmacc.vf      v20, ft10, v24
    vfwmacc.vf      v22, ft11, v24

    addi            a6, a6, 2
    addi            a7, a7, 2
    addi            t2, t2, 1

    mv              a0, t2
    .word           0x00057cdb  // vakv2kcol v25, dimension(a0)

    flh             ft0, 0(a6)
    flh             ft1, 256(a6)
    flh             ft2, 512(a6)
    flh             ft3, 768(a6)
    flh             ft4, 1024(a6)
    flh             ft5, 1280(a6)
    flh             ft6, 0(a7)
    flh             ft7, 256(a7)
    flh             ft8, 512(a7)
    flh             ft9, 768(a7)
    flh             ft10, 1024(a7)
    flh             ft11, 1280(a7)
    vfwmacc.vf      v0, ft0, v25
    vfwmacc.vf      v2, ft1, v25
    vfwmacc.vf      v4, ft2, v25
    vfwmacc.vf      v6, ft3, v25
    vfwmacc.vf      v8, ft4, v25
    vfwmacc.vf      v10, ft5, v25
    vfwmacc.vf      v12, ft6, v25
    vfwmacc.vf      v14, ft7, v25
    vfwmacc.vf      v16, ft8, v25
    vfwmacc.vf      v18, ft9, v25
    vfwmacc.vf      v20, ft10, v25
    vfwmacc.vf      v22, ft11, v25

    addi            a6, a6, 2
    addi            a7, a7, 2
    addi            t2, t2, 1
    bltu            t2, t3, .Lakv_v2_q2_score_dimension_pair

    vsetvli         zero, t1, e32, m2, ta, ma
    mv              t4, t0
    li              t5, 2048
    add             t5, t0, t5
    vse32.v         v0, (t4)
    addi            t4, t4, 256
    vse32.v         v2, (t4)
    addi            t4, t4, 256
    vse32.v         v4, (t4)
    addi            t4, t4, 256
    vse32.v         v6, (t4)
    addi            t4, t4, 256
    vse32.v         v8, (t4)
    addi            t4, t4, 256
    vse32.v         v10, (t4)
    vse32.v         v12, (t5)
    addi            t5, t5, 256
    vse32.v         v14, (t5)
    addi            t5, t5, 256
    vse32.v         v16, (t5)
    addi            t5, t5, 256
    vse32.v         v18, (t5)
    addi            t5, t5, 256
    vse32.v         v20, (t5)
    addi            t5, t5, 256
    vse32.v         v22, (t5)
    ret

    .size akv_v2_compute_scores_f16_d128_gqa6_q2, \
          .-akv_v2_compute_scores_f16_d128_gqa6_q2

    .globl  akv_v2_compute_scores_f16_d128_gqa6_q2_panel4
    .type   akv_v2_compute_scores_f16_d128_gqa6_q2_panel4,@function

// Panel4 preserves the Q2 arithmetic and score layout above, but each custom
// command exposes four adjacent K columns in one LMUL=4 destination group.
// Alternating v24-v27 and v28-v31 keeps a following panel load independent of
// the immediately preceding panel's RVV consumers.
// a0: first six-row F16 D128 Query group
// a1: second six-row F16 D128 Query group
// a2: two six-row F32 score sets
// a3: active token count for the later Query, 1..64

    .macro AKV_Q2_PANEL_COLUMN vreg
    flh             ft0, 0(a6)
    flh             ft1, 256(a6)
    flh             ft2, 512(a6)
    flh             ft3, 768(a6)
    flh             ft4, 1024(a6)
    flh             ft5, 1280(a6)
    flh             ft6, 0(a7)
    flh             ft7, 256(a7)
    flh             ft8, 512(a7)
    flh             ft9, 768(a7)
    flh             ft10, 1024(a7)
    flh             ft11, 1280(a7)
    vfwmacc.vf      v0, ft0, \vreg
    vfwmacc.vf      v2, ft1, \vreg
    vfwmacc.vf      v4, ft2, \vreg
    vfwmacc.vf      v6, ft3, \vreg
    vfwmacc.vf      v8, ft4, \vreg
    vfwmacc.vf      v10, ft5, \vreg
    vfwmacc.vf      v12, ft6, \vreg
    vfwmacc.vf      v14, ft7, \vreg
    vfwmacc.vf      v16, ft8, \vreg
    vfwmacc.vf      v18, ft9, \vreg
    vfwmacc.vf      v20, ft10, \vreg
    vfwmacc.vf      v22, ft11, \vreg
    addi            a6, a6, 2
    addi            a7, a7, 2
    .endm

akv_v2_compute_scores_f16_d128_gqa6_q2_panel4:
    mv              a6, a0
    mv              a7, a1
    mv              t0, a2
    mv              t1, a3

    vsetvli         zero, t1, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vmv.v.i         v2, 0
    vmv.v.i         v4, 0
    vmv.v.i         v6, 0
    vmv.v.i         v8, 0
    vmv.v.i         v10, 0
    vmv.v.i         v12, 0
    vmv.v.i         v14, 0
    vmv.v.i         v16, 0
    vmv.v.i         v18, 0
    vmv.v.i         v20, 0
    vmv.v.i         v22, 0

    vsetvli         zero, t1, e16, m1, ta, ma
    li              t2, 0
    li              t3, 128
.Lakv_v2_q2_score_dimension_panel_pair:
    mv              a0, t2
    .word           0x02057c5b  // vakv2kpanel4 v24, dimension(a0)
    AKV_Q2_PANEL_COLUMN v24
    AKV_Q2_PANEL_COLUMN v25
    AKV_Q2_PANEL_COLUMN v26
    AKV_Q2_PANEL_COLUMN v27
    addi            t2, t2, 4

    mv              a0, t2
    .word           0x02057e5b  // vakv2kpanel4 v28, dimension(a0)
    AKV_Q2_PANEL_COLUMN v28
    AKV_Q2_PANEL_COLUMN v29
    AKV_Q2_PANEL_COLUMN v30
    AKV_Q2_PANEL_COLUMN v31
    addi            t2, t2, 4
    bltu            t2, t3, .Lakv_v2_q2_score_dimension_panel_pair

    vsetvli         zero, t1, e32, m2, ta, ma
    mv              t4, t0
    li              t5, 2048
    add             t5, t0, t5
    vse32.v         v0, (t4)
    addi            t4, t4, 256
    vse32.v         v2, (t4)
    addi            t4, t4, 256
    vse32.v         v4, (t4)
    addi            t4, t4, 256
    vse32.v         v6, (t4)
    addi            t4, t4, 256
    vse32.v         v8, (t4)
    addi            t4, t4, 256
    vse32.v         v10, (t4)
    vse32.v         v12, (t5)
    addi            t5, t5, 256
    vse32.v         v14, (t5)
    addi            t5, t5, 256
    vse32.v         v16, (t5)
    addi            t5, t5, 256
    vse32.v         v18, (t5)
    addi            t5, t5, 256
    vse32.v         v20, (t5)
    addi            t5, t5, 256
    vse32.v         v22, (t5)
    ret

    .size akv_v2_compute_scores_f16_d128_gqa6_q2_panel4, \
          .-akv_v2_compute_scores_f16_d128_gqa6_q2_panel4
    .purgem AKV_Q2_PANEL_COLUMN

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
    addi            a4, a4, 512
    vle16.v         v2, (a4)
    addi            a4, a4, 512
    vle16.v         v4, (a4)
    addi            a4, a4, 512
    vle16.v         v6, (a4)
    addi            a4, a4, 512
    vle16.v         v10, (a4)
    addi            a4, a4, 512
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
    addi            a4, a4, 512
    vse16.v         v2, (a4)
    addi            a4, a4, 512
    vse16.v         v4, (a4)
    addi            a4, a4, 512
    vse16.v         v6, (a4)
    addi            a4, a4, 512
    vse16.v         v10, (a4)
    addi            a4, a4, 512
    vse16.v         v12, (a4)
    ret

    .size akv_v2_update_outputs_f16_d128_gqa6, \
          .-akv_v2_update_outputs_f16_d128_gqa6

    .globl  akv_v2_compute_scores_f16_generic
    .type   akv_v2_compute_scores_f16_generic,@function

// a0: F16 Query rows, a1: F32 score rows (64-element stride)
// a2: active tokens, a3: Query stride, a4: Q rows, a5: head dimension
akv_v2_compute_scores_f16_generic:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    mv              t4, a4
    mv              t5, a5
.Lakv_v2_generic_score_head:
    vsetvli         zero, t2, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vsetvli         zero, t2, e16, m1, ta, ma
    mv              a6, t0
    li              a7, 0
.Lakv_v2_generic_score_dimension:
    mv              a0, a7
    .word           0x0005745b  // vakv2kcol v8, dimension(a0)
    flh             ft0, 0(a6)
    vfwmacc.vf      v0, ft0, v8
    addi            a6, a6, 2
    addi            a7, a7, 1
    bltu            a7, t5, .Lakv_v2_generic_score_dimension
    vsetvli         zero, t2, e32, m2, ta, ma
    vse32.v         v0, (t1)
    add             t0, t0, t3
    addi            t1, t1, 256
    addi            t4, t4, -1
    bnez            t4, .Lakv_v2_generic_score_head
    ret

    .size akv_v2_compute_scores_f16_generic, \
          .-akv_v2_compute_scores_f16_generic

    .globl  akv_v2_compute_scores_f32_generic
    .type   akv_v2_compute_scores_f32_generic,@function

// a0: F32 Query rows, a1: F32 score rows (64-element stride)
// a2: active tokens, a3: Query stride, a4: Q rows, a5: head dimension
akv_v2_compute_scores_f32_generic:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    mv              t4, a4
    mv              t5, a5
.Lakv_v2_generic_f32_score_head:
    vsetvli         zero, t2, e32, m2, ta, ma
    vmv.v.i         v0, 0
    mv              a6, t0
    li              a7, 0
.Lakv_v2_generic_f32_score_dimension:
    vsetvli         zero, t2, e16, m1, ta, ma
    mv              a0, a7
    .word           0x0005745b  // vakv2kcol v8, dimension(a0)
    vfwcvt.f.f.v    v10, v8
    flw             ft0, 0(a6)
    vsetvli         zero, t2, e32, m2, ta, ma
    vfmacc.vf       v0, ft0, v10
    addi            a6, a6, 4
    addi            a7, a7, 1
    bltu            a7, t5, .Lakv_v2_generic_f32_score_dimension
    vse32.v         v0, (t1)
    add             t0, t0, t3
    addi            t1, t1, 256
    addi            t4, t4, -1
    bnez            t4, .Lakv_v2_generic_f32_score_head
    ret

    .size akv_v2_compute_scores_f32_generic, \
          .-akv_v2_compute_scores_f32_generic

    .globl  akv_v2_compute_scores_f32_d128_gqa2_panel4
    .type   akv_v2_compute_scores_f32_d128_gqa2_panel4,@function

// Two GQA rows share each resident K panel. F32 Query values preserve GGML's
// Prefill input contract while K remains in its captured F16 representation.
// a0: first F32 D128 Query row, a1: two F32 score rows
// a2: active tokens, a3: Query row stride in bytes
akv_v2_compute_scores_f32_d128_gqa2_panel4:
    mv              a4, a0
    add             a5, a4, a3
    mv              t0, a1
    mv              t1, a2

    vsetvli         zero, t1, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vmv.v.i         v2, 0

    li              t2, 0
    li              t3, 128
.Lakv_v2_f32_gqa2_score_panel:
    vsetvli         zero, t1, e16, m1, ta, ma
    mv              a0, t2
    .word           0x0205745b  // vakv2kpanel4 v8:v11, dimension(a0)
    vfwcvt.f.f.v    v16, v8
    vfwcvt.f.f.v    v18, v9
    vfwcvt.f.f.v    v20, v10
    vfwcvt.f.f.v    v22, v11

    flw             ft0, 0(a4)
    flw             ft1, 4(a4)
    flw             ft2, 8(a4)
    flw             ft3, 12(a4)
    flw             ft4, 0(a5)
    flw             ft5, 4(a5)
    flw             ft6, 8(a5)
    flw             ft7, 12(a5)
    vsetvli         zero, t1, e32, m2, ta, ma
    vfmacc.vf       v0, ft0, v16
    vfmacc.vf       v0, ft1, v18
    vfmacc.vf       v0, ft2, v20
    vfmacc.vf       v0, ft3, v22
    vfmacc.vf       v2, ft4, v16
    vfmacc.vf       v2, ft5, v18
    vfmacc.vf       v2, ft6, v20
    vfmacc.vf       v2, ft7, v22

    addi            a4, a4, 16
    addi            a5, a5, 16
    addi            t2, t2, 4
    bltu            t2, t3, .Lakv_v2_f32_gqa2_score_panel

    vse32.v         v0, (t0)
    addi            t0, t0, 256
    vse32.v         v2, (t0)
    ret

    .size akv_v2_compute_scores_f32_d128_gqa2_panel4, \
          .-akv_v2_compute_scores_f32_d128_gqa2_panel4

    .globl  akv_v2_update_outputs_f16_generic
    .type   akv_v2_update_outputs_f16_generic,@function

// a0: F32 softmax rows, a1: F16 accumulators, a2: old scales
// a3: active tokens, a4: Q rows, a5: head dimension
akv_v2_update_outputs_f16_generic:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    mv              t4, a4
    mv              t5, a5
.Lakv_v2_generic_output_head:
    vsetvli         zero, t5, e16, m2, ta, ma
    vle16.v         v0, (t1)
    flw             ft0, 0(t2)
    fcvt.h.s        ft0, ft0
    vfmul.vf        v0, v0, ft0
    mv              a7, t0
    li              a6, 0
.Lakv_v2_generic_value_token:
    flw             ft0, 0(a7)
    fcvt.h.s        ft0, ft0
    slli            a0, a6, 2
    ori             a0, a0, 2
    li              a1, 64
    beq             t5, a1, .Lakv_v2_generic_load_d64
    li              a1, 96
    beq             t5, a1, .Lakv_v2_generic_load_d96
    .word           0x0205345b  // vakvload.d128 v8:v9, V selector(a0)
    j               .Lakv_v2_generic_value_loaded
.Lakv_v2_generic_load_d96:
    .word           0x0405345b  // vakvload.d96 v8:v9, V selector(a0)
    j               .Lakv_v2_generic_value_loaded
.Lakv_v2_generic_load_d64:
    .word           0x0005345b  // vakvload.d64 v8, V selector(a0)
.Lakv_v2_generic_value_loaded:
    vfmacc.vf       v0, ft0, v8
    addi            a7, a7, 4
    addi            a6, a6, 1
    bltu            a6, t3, .Lakv_v2_generic_value_token
    vse16.v         v0, (t1)
    // The shared workspace reserves D256 for every row, independent of the
    // active D64/D96/D128 operation.
    addi            t1, t1, 512
    addi            t0, t0, 256
    addi            t2, t2, 4
    addi            t4, t4, -1
    bnez            t4, .Lakv_v2_generic_output_head
    ret

    .size akv_v2_update_outputs_f16_generic, \
          .-akv_v2_update_outputs_f16_generic

    .globl  akv_v2_update_outputs_f32_d128_gqa6
    .type   akv_v2_update_outputs_f32_d128_gqa6,@function

// a0: six row-major F32 softmax-weight rows, each with a 64-element stride
// a1: six contiguous row-major F32 D128 output numerators
// a2: six F32 old-state scale factors
// a3: active token count, 1..64
akv_v2_update_outputs_f32_d128_gqa6:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3

    li              t4, 128
    vsetvli         zero, t4, e32, m4, ta, ma
    mv              a4, t1
    vle32.v         v0, (a4)
    addi            a4, a4, 512
    vle32.v         v4, (a4)
    addi            a4, a4, 512
    vle32.v         v8, (a4)
    addi            a4, a4, 512
    vle32.v         v12, (a4)
    addi            a4, a4, 512
    vle32.v         v16, (a4)
    addi            a4, a4, 512
    vle32.v         v20, (a4)

    flw             ft0, 0(t2)
    flw             ft1, 4(t2)
    flw             ft2, 8(t2)
    flw             ft3, 12(t2)
    flw             ft4, 16(t2)
    flw             ft5, 20(t2)
    vfmul.vf        v0, v0, ft0
    vfmul.vf        v4, v4, ft1
    vfmul.vf        v8, v8, ft2
    vfmul.vf        v12, v12, ft3
    vfmul.vf        v16, v16, ft4
    vfmul.vf        v20, v20, ft5

    li              t4, 0
.Lakv_v2_f32_value_token:
    flw             ft0, 0(t0)
    flw             ft1, 256(t0)
    flw             ft2, 512(t0)
    flw             ft3, 768(t0)
    flw             ft4, 1024(t0)
    flw             ft5, 1280(t0)

    li              a5, 128
    vsetvli         zero, a5, e16, m2, ta, ma
    slli            a0, t4, 2
    ori             a0, a0, 2
    .word           0x02053c5b  // vakvload.d128 v24:v25, V selector(a0)
    vfwcvt.f.f.v    v28, v24
    vsetvli         zero, a5, e32, m4, ta, ma
    vfmacc.vf       v0, ft0, v28
    vfmacc.vf       v4, ft1, v28
    vfmacc.vf       v8, ft2, v28
    vfmacc.vf       v12, ft3, v28
    vfmacc.vf       v16, ft4, v28
    vfmacc.vf       v20, ft5, v28

    addi            t0, t0, 4
    addi            t4, t4, 1
    bltu            t4, t3, .Lakv_v2_f32_value_token

    mv              a4, t1
    vse32.v         v0, (a4)
    addi            a4, a4, 512
    vse32.v         v4, (a4)
    addi            a4, a4, 512
    vse32.v         v8, (a4)
    addi            a4, a4, 512
    vse32.v         v12, (a4)
    addi            a4, a4, 512
    vse32.v         v16, (a4)
    addi            a4, a4, 512
    vse32.v         v20, (a4)
    ret

    .size akv_v2_update_outputs_f32_d128_gqa6, \
          .-akv_v2_update_outputs_f32_d128_gqa6

    .globl  akv_v2_update_outputs_f32_generic
    .type   akv_v2_update_outputs_f32_generic,@function

// a0: F32 softmax rows, a1: contiguous F32 numerators, a2: old scales
// a3: active tokens, a4: Q rows, a5: head dimension (64, 96, or 128)
akv_v2_update_outputs_f32_generic:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    mv              t4, a4
    mv              t5, a5
.Lakv_v2_generic_f32_output_head:
    vsetvli         zero, t5, e32, m4, ta, ma
    vle32.v         v0, (t1)
    flw             ft0, 0(t2)
    vfmul.vf        v0, v0, ft0
    mv              a7, t0
    li              a6, 0
.Lakv_v2_generic_f32_value_token:
    flw             ft0, 0(a7)
    vsetvli         zero, t5, e16, m2, ta, ma
    slli            a0, a6, 2
    ori             a0, a0, 2
    li              a1, 64
    beq             t5, a1, .Lakv_v2_generic_f32_load_d64
    li              a1, 96
    beq             t5, a1, .Lakv_v2_generic_f32_load_d96
    .word           0x0205345b  // vakvload.d128 v8:v9, V selector(a0)
    j               .Lakv_v2_generic_f32_value_loaded
.Lakv_v2_generic_f32_load_d96:
    .word           0x0405345b  // vakvload.d96 v8:v9, V selector(a0)
    j               .Lakv_v2_generic_f32_value_loaded
.Lakv_v2_generic_f32_load_d64:
    .word           0x0005345b  // vakvload.d64 v8, V selector(a0)
.Lakv_v2_generic_f32_value_loaded:
    vfwcvt.f.f.v    v12, v8
    vsetvli         zero, t5, e32, m4, ta, ma
    vfmacc.vf       v0, ft0, v12
    addi            a7, a7, 4
    addi            a6, a6, 1
    bltu            a6, t3, .Lakv_v2_generic_f32_value_token
    vse32.v         v0, (t1)
    slli            a0, t5, 2
    add             t1, t1, a0
    addi            t0, t0, 256
    addi            t2, t2, 4
    addi            t4, t4, -1
    bnez            t4, .Lakv_v2_generic_f32_output_head
    ret

    .size akv_v2_update_outputs_f32_generic, \
          .-akv_v2_update_outputs_f32_generic

    .globl  akv_v2_compute_scores_f16_d256_generic
    .type   akv_v2_compute_scores_f16_d256_generic,@function

// D256 is represented by two resident D128 columns. Selector bit 7 chooses
// the second physical segment while bits 6:0 retain the local dimension.
// a0: F16 Query rows, a1: F32 score rows (64-element stride)
// a2: active tokens, a3: Query stride, a4: Q rows
akv_v2_compute_scores_f16_d256_generic:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    mv              t4, a4
.Lakv_v2_d256_score_head:
    vsetvli         zero, t2, e32, m2, ta, ma
    vmv.v.i         v0, 0
    vsetvli         zero, t2, e16, m1, ta, ma
    mv              a6, t0
    li              a7, 0
    li              t5, 256
.Lakv_v2_d256_score_dimension:
    mv              a0, a7
    .word           0x0005745b  // vakv2col v8, {segment,dimension}(a0)
    flh             ft0, 0(a6)
    vfwmacc.vf      v0, ft0, v8
    addi            a6, a6, 2
    addi            a7, a7, 1
    bltu            a7, t5, .Lakv_v2_d256_score_dimension
    vsetvli         zero, t2, e32, m2, ta, ma
    vse32.v         v0, (t1)
    add             t0, t0, t3
    addi            t1, t1, 256
    addi            t4, t4, -1
    bnez            t4, .Lakv_v2_d256_score_head
    ret

    .size akv_v2_compute_scores_f16_d256_generic, \
          .-akv_v2_compute_scores_f16_d256_generic

    .globl  akv_v2_update_outputs_f16_d256_generic
    .type   akv_v2_update_outputs_f16_d256_generic,@function

// The value-phase descriptor maps V[0:128] to the physical K rows and
// V[128:256] to the physical V rows. Both halves consume identical weights.
// a0: F32 softmax rows, a1: F16 D256 accumulators, a2: old scales
// a3: active tokens, a4: Q rows
akv_v2_update_outputs_f16_d256_generic:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    mv              t3, a3
    mv              t4, a4
.Lakv_v2_d256_output_head:
    li              t5, 128
    vsetvli         zero, t5, e16, m2, ta, ma
    vle16.v         v0, (t1)
    addi            t6, t1, 256
    vle16.v         v2, (t6)
    vfwcvt.f.f.v    v4, v0
    vsetvli         zero, t5, e32, m4, ta, ma
    flw             ft0, 0(t2)
    vfmul.vf        v4, v4, ft0
    vsetvli         zero, t5, e16, m2, ta, ma
    vfncvt.f.f.w    v0, v4
    vfwcvt.f.f.v    v4, v2
    vsetvli         zero, t5, e32, m4, ta, ma
    vfmul.vf        v4, v4, ft0
    vsetvli         zero, t5, e16, m2, ta, ma
    vfncvt.f.f.w    v2, v4
    mv              a7, t0
    li              a6, 0
.Lakv_v2_d256_value_token:
    flw             ft0, 0(a7)
    vsetvli         zero, t5, e16, m2, ta, ma
    slli            a0, a6, 2
    ori             a0, a0, 1
    .word           0x0205345b  // vakvload.d128 v8:v9, segment 0 row
    vfwcvt.f.f.v    v4, v0
    vfwcvt.f.f.v    v12, v8
    vsetvli         zero, t5, e32, m4, ta, ma
    vfmacc.vf       v4, ft0, v12
    vsetvli         zero, t5, e16, m2, ta, ma
    vfncvt.f.f.w    v0, v4
    addi            a0, a0, 1
    .word           0x0205345b  // vakvload.d128 v8:v9, segment 1 row
    vfwcvt.f.f.v    v4, v2
    vfwcvt.f.f.v    v12, v8
    vsetvli         zero, t5, e32, m4, ta, ma
    vfmacc.vf       v4, ft0, v12
    vsetvli         zero, t5, e16, m2, ta, ma
    vfncvt.f.f.w    v2, v4
    addi            a7, a7, 4
    addi            a6, a6, 1
    bltu            a6, t3, .Lakv_v2_d256_value_token
    vse16.v         v0, (t1)
    vse16.v         v2, (t6)
    addi            t1, t1, 512
    addi            t0, t0, 256
    addi            t2, t2, 4
    addi            t4, t4, -1
    bnez            t4, .Lakv_v2_d256_output_head
    ret

    .size akv_v2_update_outputs_f16_d256_generic, \
          .-akv_v2_update_outputs_f16_d256_generic
