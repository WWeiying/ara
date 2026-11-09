// Candidate preparation only; no custom instruction, result store, or SDK change.
// a0=F32 coefficients, a1=F16 seeds, a2=F32 scales[2], a3=T, a4=D, a5=H.
// Input row/head strides: coefficients 256B, seeds 512B, scales 4B.
// Preconditions: VLEN1024, T=1..64, D=64/96/128, H=1/2, vstart=0, frm=0..4.
// Caller validates accessible/aligned input spans and V/Zfh/Zvfh availability.
// Outputs: v8:v9 seed0, v10:v11 seed1, v12:v13 interleaved raw F16 pairs.
// Preserves a0-a5, ra, sp, frm, and existing fflags; accrues active FP flags.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl resident_pv_prepare
    .type resident_pv_prepare,@function
resident_pv_prepare:
    // Define both entire fixed-stride seed groups as EW16 using integer work.
    // D64's second register and H1's second head must not hide later maintenance.
    li              t0, 128
    vsetvli         zero, t0, e16, m2, ta, ma
    vmv.v.i         v8, 0
    vmv.v.i         v10, 0
    vsetvli         zero, a4, e16, m2, tu, ma
    vle16.v         v8, (a1)
    li              t1, 1
    beq             a5, t1, .Lscale_head0
    addi            t0, a1, 512
    vle16.v         v10, (t0)
.Lscale_head0:
    flw             ft0, 0(a2)
    fcvt.h.s        ft0, ft0, dyn
    vfmul.vf        v8, v8, ft0
    beq             a5, t1, .Lcoefficient_load
    flw             ft1, 4(a2)
    fcvt.h.s        ft1, ft1, dyn
    vfmul.vf        v10, v10, ft1
.Lcoefficient_load:
    vsetvli         zero, a3, e32, m2, ta, ma
    vle32.v         v16, (a0)
    beq             a5, t1, .Lcoefficient_h1
    addi            t0, a0, 256
    vle32.v         v18, (t0)
    vsetvli         zero, a3, e16, m1, ta, ma
    vfncvt.f.f.w    v20, v16
    vfncvt.f.f.w    v21, v18
    j               .Lpack
.Lcoefficient_h1:
    vsetvli         zero, a3, e16, m1, ta, ma
    vfncvt.f.f.w    v20, v16
    vmv.v.i         v21, 0
.Lpack:
    // Zero-extend RAW halfword bits, not FP values. Widening destinations have
    // EEW32/EMUL2 while the current vtype remains e16/m1 and VL remains T.
    vwaddu.vx       v12, v20, zero
    vwaddu.vx       v14, v21, zero
    vsetvli         zero, a3, e32, m2, ta, ma
    vsll.vi         v14, v14, 16
    vor.vv          v12, v12, v14
    // This real EW16 read/write belongs inside measured preparation. It covers
    // both coefficient registers even when T<32. Inactive bits never enter FP.
    li              t0, 128
    vsetvli         zero, t0, e16, m2, ta, ma
    vor.vv          v12, v12, v12
    ret
    .size resident_pv_prepare, .-resident_pv_prepare
    .option pop
    .section .note.GNU-stack,"",@progbits
