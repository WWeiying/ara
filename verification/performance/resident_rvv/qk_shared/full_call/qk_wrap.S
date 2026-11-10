// Fixed H2/base0 real-input experiment; production selection is separate.
// Preserve the original panel4 implementation on the baseline arm.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl __wrap_akv_experimental_qk_f16_pair_panel4
    .type __wrap_akv_experimental_qk_f16_pair_panel4,@function
__wrap_akv_experimental_qk_f16_pair_panel4:
    la      t0, resident_pv_rotation_selected
    lw      t0, 0(t0)
    beqz    t0, .Loriginal_qk
    // Original arguments: query, scores, T, query-byte-stride, D.
    // Context FULL already loaded both query rows; no new memory transfer.
    mv      a0, a1
    mv      a1, a2
    li      a2, 2
    mv      a3, a4
    li      a4, 0
    tail    akv_experimental_resident_qk
.Loriginal_qk:
    tail    __real_akv_experimental_qk_f16_pair_panel4
    .size __wrap_akv_experimental_qk_f16_pair_panel4, .-__wrap_akv_experimental_qk_f16_pair_panel4
    .option pop
    .section .note.GNU-stack,"",@progbits
