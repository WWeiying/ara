/* Exactly the established full_call baseline, only when mode 4 is selected. */
    .text
    .p2align 2
    .globl __wrap_akv_experimental_pv_f16_pair
    .type __wrap_akv_experimental_pv_f16_pair,@function
__wrap_akv_experimental_pv_f16_pair:
    la t0, attention_strong_replay
    lw t0, 0(t0)
    bnez t0, 1f
    tail __real_akv_experimental_pv_f16_pair
1:
    tail attention_replay_pv_rotation
    .size __wrap_akv_experimental_pv_f16_pair, .-__wrap_akv_experimental_pv_f16_pair
    .section .note.GNU-stack,"",@progbits
