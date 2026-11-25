// Stackless successor. Payload bytes, excluding RET, must match pv_prepare.S;
// test_low_overhead.py checks this against the actual assembled objects.
// t6 holds the scalar control across the unchanged preparation instructions.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl akv_experimental_resident_pv_prepared
    .type akv_experimental_resident_pv_prepared,@function
// a0-a5 retain the fast ABI; a6 is the validated tile's PV control.
akv_experimental_resident_pv_prepared:
    mv              t6, a6
    j               .Lfast_payload
    .size akv_experimental_resident_pv_prepared, .-akv_experimental_resident_pv_prepared
    .globl akv_experimental_resident_pv_fast
    .type akv_experimental_resident_pv_fast,@function
akv_experimental_resident_pv_fast:
    addi            t6, a3, -1
    addi            t0, a5, -1
    slli            t0, t0, 6
    or              t6, t6, t0
    li              t0, 64
    beq             a4, t0, .Lfast_payload
    li              t0, 96
    beq             a4, t0, .Lfast_d96
    ori             t6, t6, 128
    j               .Lfast_payload
.Lfast_d96:
    ori             t6, t6, 256
.Lfast_payload:
    li              t0, 128
    vsetvli         zero, t0, e16, m2, ta, ma
    vmv.v.i         v8, 0
    vmv.v.i         v10, 0
    vsetvli         zero, a4, e16, m2, tu, ma
    vle16.v         v8, (a1)
    li              t1, 1
    beq             a5, t1, .Lfast_scale_head0
    addi            t0, a1, 512
    vle16.v         v10, (t0)
.Lfast_scale_head0:
    flw             ft0, 0(a2)
    fcvt.h.s        ft0, ft0, dyn
    vfmul.vf        v8, v8, ft0
    beq             a5, t1, .Lfast_coefficient_load
    flw             ft1, 4(a2)
    fcvt.h.s        ft1, ft1, dyn
    vfmul.vf        v10, v10, ft1
.Lfast_coefficient_load:
    vsetvli         zero, a3, e32, m2, ta, ma
    vle32.v         v16, (a0)
    beq             a5, t1, .Lfast_coefficient_h1
    addi            t0, a0, 256
    vle32.v         v18, (t0)
    vsetvli         zero, a3, e16, m1, ta, ma
    vfncvt.f.f.w    v20, v16
    vfncvt.f.f.w    v21, v18
    j               .Lfast_pack
.Lfast_coefficient_h1:
    vsetvli         zero, a3, e16, m1, ta, ma
    vfncvt.f.f.w    v20, v16
    vmv.v.i         v21, 0
.Lfast_pack:
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
    beq             a5, t0, .Lfast_done
    addi            t0, a1, 512
    vse16.v         v2, (t0)
.Lfast_done:
    ret
    .size akv_experimental_resident_pv_fast, .-akv_experimental_resident_pv_fast
    .option pop
    .section .note.GNU-stack,"",@progbits
