// Experimental PV: a0=F32 probabilities, a1=F16 accumulator, a2=F32 scales,
// a3=T, a4=D, a5=H. Caller establishes the preconditions in pv.h.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl akv_experimental_resident_pv
    .type akv_experimental_resident_pv,@function
akv_experimental_resident_pv:
    addi            sp, sp, -32
    sd              ra, 0(sp)
    sd              a1, 8(sp)
    sd              a4, 16(sp)
    sd              a5, 24(sp)
    call            akv_experimental_resident_pv_prepare
    // No C call or vector instruction may disturb the prepared v8-v13 payload.
    addi            a0, a3, -1
    addi            t0, a5, -1
    slli            t0, t0, 6
    or              a0, a0, t0
    li              t0, 64
    beq             a4, t0, .Lsdk_pv_issue
    li              t0, 96
    beq             a4, t0, .Lsdk_pv_d96
    ori             a0, a0, 128
    j               .Lsdk_pv_issue
.Lsdk_pv_d96:
    ori             a0, a0, 256
.Lsdk_pv_issue:
    .word           0x0485705b  // custom2/7/2, vd=v0, rs1=a0, vs2=v8
    ld              a1, 8(sp)
    ld              a4, 16(sp)
    ld              a5, 24(sp)
    vsetvli         zero, a4, e16, m2, ta, ma
    vse16.v         v0, (a1)
    li              t0, 1
    beq             a5, t0, .Lsdk_pv_done
    addi            t0, a1, 512
    vse16.v         v2, (t0)
.Lsdk_pv_done:
    ld              ra, 0(sp)
    addi            sp, sp, 32
    ret
    .size akv_experimental_resident_pv, .-akv_experimental_resident_pv
    .option pop

// Keep the sealed preparation bytes unchanged; namespace only at preprocessing.
#define resident_pv_prepare akv_experimental_resident_pv_prepare
#include "pv_prepare.S"
#undef resident_pv_prepare
    .hidden akv_experimental_resident_pv_prepare

#include "pv_fast.inc"
