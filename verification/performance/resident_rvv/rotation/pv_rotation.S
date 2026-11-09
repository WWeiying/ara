// Diagnostic only: the arithmetic order is unchanged; V rows alternate groups.
    .text
    .p2align 2
    .globl __wrap_akv_experimental_pv_f16_pair
    .type __wrap_akv_experimental_pv_f16_pair,@function

    .macro ROTATION_ROW reg
    flw             ft0, 0(t0)
    fcvt.h.s        ft0, ft0
    flw             ft1, 256(t0)
    fcvt.h.s        ft1, ft1
    slli            a0, t4, 2
    ori             a0, a0, 2
    li              a1, 64
    beq             t5, a1, .Lrotation_d64_\@
    li              a1, 96
    beq             t5, a1, .Lrotation_d96_\@
    .word           0x0205305b | (\reg << 7)
    j               .Lrotation_loaded_\@
.Lrotation_d96_\@:
    .word           0x0405305b | (\reg << 7)
    j               .Lrotation_loaded_\@
.Lrotation_d64_\@:
    .word           0x0005305b | (\reg << 7)
.Lrotation_loaded_\@:
    vfmacc.vf       v0, ft0, v\reg
    vfmacc.vf       v2, ft1, v\reg
    addi            t0, t0, 4
    addi            t4, t4, 1
    .endm

__wrap_akv_experimental_pv_f16_pair:
    la              t6, resident_pv_rotation_selected
    lw              t6, 0(t6)
    bnez            t6, .Lrotation_setup
    j               __real_akv_experimental_pv_f16_pair
.Lrotation_setup:
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
.Lrotation_pair:
    ROTATION_ROW    8
    bgeu            t4, t3, .Lrotation_done
    ROTATION_ROW    10
    bltu            t4, t3, .Lrotation_pair
.Lrotation_done:
    vse16.v         v0, (t1)
    vse16.v         v2, (a4)
    ret
    .size __wrap_akv_experimental_pv_f16_pair, .-__wrap_akv_experimental_pv_f16_pair
    .purgem ROTATION_ROW
    .section .note.GNU-stack,"",@progbits
