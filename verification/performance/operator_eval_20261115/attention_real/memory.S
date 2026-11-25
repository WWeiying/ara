/* full_call paired-head instruction schedule, with ordinary memory loads.
 * K transpose is included in the timed call. No AKV opcodes in these leaves. */
    .text
    .p2align 2
    .globl attention_memory_qk_panel4
    .type attention_memory_qk_panel4,@function
    .macro COLUMN reg
    flh ft0, 0(a4)
    flh ft1, 0(a5)
    vfwmacc.vf v0, ft0, \reg
    vfwmacc.vf v2, ft1, \reg
    addi a4, a4, 2
    addi a5, a5, 2
    .endm
attention_memory_qk_panel4:
    mv t5, a4
    mv t3, a5
    mv a4, a0
    add a5, a0, a3
    mv t0, a1
    mv t1, a2
    vsetvli zero, t1, e32, m2, ta, ma
    vmv.v.i v0, 0
    vmv.v.i v2, 0
    vsetvli zero, t1, e16, m1, ta, ma
    li t2, 0
1:
    vle16.v v8, (t3)
    addi t3, t3, 128
    vle16.v v9, (t3)
    addi t3, t3, 128
    vle16.v v10, (t3)
    addi t3, t3, 128
    vle16.v v11, (t3)
    addi t3, t3, 128
    COLUMN v8
    COLUMN v9
    COLUMN v10
    COLUMN v11
    addi t2, t2, 4
    bltu t2, t5, 1b
    vsetvli zero, t1, e32, m2, ta, ma
    vse32.v v0, (t0)
    addi t0, t0, 256
    vse32.v v2, (t0)
    ret
    .size attention_memory_qk_panel4, .-attention_memory_qk_panel4
    .purgem COLUMN

    .p2align 2
    .globl attention_memory_pv_rotation
    .type attention_memory_pv_rotation,@function
    .macro ROW reg
    flw ft0, 0(t0)
    fcvt.h.s ft0, ft0
    flw ft1, 256(t0)
    fcvt.h.s ft1, ft1
    vle16.v v\reg, (a5)
    add a5, a5, a6
    vfmacc.vf v0, ft0, v\reg
    vfmacc.vf v2, ft1, v\reg
    addi t0, t0, 4
    addi t4, t4, 1
    .endm
attention_memory_pv_rotation:
    mv t5, a4
    mv t0, a0
    mv t1, a1
    mv t2, a2
    mv t3, a3
    addi a4, t1, 512
    vsetvli zero, t5, e16, m2, ta, ma
    vle16.v v0, (t1)
    vle16.v v2, (a4)
    flw ft0, 0(t2)
    fcvt.h.s ft0, ft0
    vfmul.vf v0, v0, ft0
    flw ft1, 4(t2)
    fcvt.h.s ft1, ft1
    vfmul.vf v2, v2, ft1
    li t4, 0
1:
    ROW 8
    bgeu t4, t3, 2f
    ROW 10
    bltu t4, t3, 1b
2:
    vse16.v v0, (t1)
    vse16.v v2, (a4)
    ret
    .size attention_memory_pv_rotation, .-attention_memory_pv_rotation
    .purgem ROW
    .section .note.GNU-stack,"",@progbits
