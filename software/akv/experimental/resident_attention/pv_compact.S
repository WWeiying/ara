// Same source layout/control/result as pv_prepared, with producer-narrowed P.
// Keep full seed initialization and final EW16 normalization: inactive import
// slots and the hardware register-layout contract are not ordinary C scratch.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl akv_experimental_resident_pv_compact
    .type akv_experimental_resident_pv_compact,@function
akv_experimental_resident_pv_compact:
    mv              t6, a6
    li              t0, 128
    vsetvli         zero, t0, e16, m2, ta, ma
    vmv.v.i         v8, 0
    vmv.v.i         v10, 0
    vsetvli         zero, a4, e16, m2, tu, ma
    vle16.v         v8, (a1)
    li              t1, 1
    beq             a5, t1, .Lcompact_scale_head0
    addi            t0, a1, 512
    vle16.v         v10, (t0)
.Lcompact_scale_head0:
    flw             ft0, 0(a2)
    fcvt.h.s        ft0, ft0, dyn
    vfmul.vf        v8, v8, ft0
    beq             a5, t1, .Lcompact_coefficient_load
    flw             ft1, 4(a2)
    fcvt.h.s        ft1, ft1, dyn
    vfmul.vf        v10, v10, ft1
.Lcompact_coefficient_load:
    vsetvli         zero, a3, e16, m1, ta, ma
    vle16.v         v20, (a0)
    beq             a5, t1, .Lcompact_coefficient_h1
    addi            t0, a0, 256
    vle16.v         v21, (t0)
    j               .Lcompact_pack
.Lcompact_coefficient_h1:
    vmv.v.i         v21, 0
.Lcompact_pack:
    vwaddu.vx       v12, v20, zero
    vwaddu.vx       v14, v21, zero
    vsetvli         zero, a3, e32, m2, ta, ma
    vsll.vi         v14, v14, 16
    vor.vv          v12, v12, v14
    li              t0, 128
    vsetvli         zero, t0, e16, m2, ta, ma
    vor.vv          v12, v12, v12
    mv              a0, t6
    .word           0x0485705b
    vsetvli         zero, a4, e16, m2, ta, ma
    vse16.v         v0, (a1)
    li              t0, 1
    beq             a5, t0, .Lcompact_done
    addi            t0, a1, 512
    vse16.v         v2, (t0)
.Lcompact_done:
    ret
    .size akv_experimental_resident_pv_compact, .-akv_experimental_resident_pv_compact
    .option pop
    .section .note.GNU-stack,"",@progbits
