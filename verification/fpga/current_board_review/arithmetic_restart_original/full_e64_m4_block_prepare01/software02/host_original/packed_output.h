#ifndef E64_M4_PACKED_OUTPUT_H
#define E64_M4_PACKED_OUTPUT_H
#include <stdint.h>

/* Definitions are a future mechanical emission of this shape's pinned
 * dictionary64.bin and indices_u16le.bin, NOT m2 data or runtime generation. */
extern const uint64_t e64m4_dictionary[1986][8];
extern const uint16_t e64m4_block_ids[5985][9];

#define E64M4_OUTPUT_STORE(index) do { \
    if(!skip_fresh(index)){output[(index)] = UINT64_C(0x5b); fresh_event(output+(index),output[(index)]);} \
    __asm__ volatile("" ::: "memory"); \
} while (0)
#define E64M4_OUTPUT_EIGHT(base) do { \
    E64M4_OUTPUT_STORE((base) + 0); \
    E64M4_OUTPUT_STORE((base) + 1); \
    E64M4_OUTPUT_STORE((base) + 2); \
    E64M4_OUTPUT_STORE((base) + 3); \
    E64M4_OUTPUT_STORE((base) + 4); \
    E64M4_OUTPUT_STORE((base) + 5); \
    E64M4_OUTPUT_STORE((base) + 6); \
    E64M4_OUTPUT_STORE((base) + 7); \
} while (0)

static inline __attribute__((always_inline)) void
e64m4_initialize_output(uint64_t output[66]) {
    E64M4_OUTPUT_EIGHT(0);
    E64M4_OUTPUT_EIGHT(8);
    E64M4_OUTPUT_EIGHT(16);
    E64M4_OUTPUT_EIGHT(24);
    E64M4_OUTPUT_EIGHT(32);
    E64M4_OUTPUT_EIGHT(40);
    E64M4_OUTPUT_EIGHT(48);
    E64M4_OUTPUT_EIGHT(56);
    E64M4_OUTPUT_STORE(64);
    E64M4_OUTPUT_STORE(65);
}

#ifndef E64M4_STATIC_STICKY_PROPOSAL_H
#define E64M4_STATIC_STICKY_PROPOSAL_H

/* Static review artifact only. Not included by any compiled candidate. */
#include <stdint.h>

extern const uint64_t e64m4_dictionary[1986][8];
extern const uint16_t e64m4_block_ids[5985][9];

#if defined(__riscv) && __riscv_xlen != 64
#error "This proposal requires the original RV64 environment"
#endif

#if defined(__riscv)
#define E64M4_STICKY_UPDATE(actual, wanted) do { \
    __asm__ volatile( \
        "beq %[actual], %[wanted], 1f\n\t" \
        "li %[bad], 1\n\t" \
        "1:\n\t" \
        : [bad] "+r" (bad) \
        : [actual] "r" (actual), [wanted] "r" (wanted) \
        : "memory"); \
} while (0)
#else
#define E64M4_STICKY_UPDATE(actual, wanted) do { \
    if ((actual) != (wanted)) bad = UINT64_C(1); \
} while (0)
#endif

#define E64M4_STICKY_WORD(index) do { \
    const uint64_t actual = current[(index)]; observe_actual(current+(index),actual); \
    const uint64_t wanted = expected[(index)]; expected_event(expected+(index),wanted); \
    E64M4_STICKY_UPDATE(actual, wanted); \
} while (0)

#define E64M4_STICKY_BLOCK(block) do { \
    const volatile uint64_t *current = output + 8 * (block); \
    const volatile uint64_t *expected = e64m4_dictionary[ids[(block)]]; \
    E64M4_STICKY_WORD(0); \
    E64M4_STICKY_WORD(1); \
    E64M4_STICKY_WORD(2); \
    E64M4_STICKY_WORD(3); \
    E64M4_STICKY_WORD(4); \
    E64M4_STICKY_WORD(5); \
    E64M4_STICKY_WORD(6); \
    E64M4_STICKY_WORD(7); \
} while (0)

static inline __attribute__((always_inline)) int
e64m4_packed_mismatch(const volatile uint64_t output[66],
                             uint64_t ordinal) {
    const uint16_t *ids = e64m4_block_ids[ordinal];
    uint64_t bad = 0;
    E64M4_STICKY_BLOCK(0);
    E64M4_STICKY_BLOCK(1);
    E64M4_STICKY_BLOCK(2);
    E64M4_STICKY_BLOCK(3);
    E64M4_STICKY_BLOCK(4);
    E64M4_STICKY_BLOCK(5);
    E64M4_STICKY_BLOCK(6);
    E64M4_STICKY_BLOCK(7);
    {
        const volatile uint64_t *current = output + 64;
        const volatile uint64_t *expected = e64m4_dictionary[ids[8]];
        E64M4_STICKY_WORD(0);
        if(monitoring && setup_variant==13){E64M4_STICKY_WORD(0);}
        else {E64M4_STICKY_WORD(1);}
    }
    return bad != 0;
}

#undef E64M4_STICKY_BLOCK
#undef E64M4_STICKY_WORD
#undef E64M4_STICKY_UPDATE
#endif

#undef E64M4_OUTPUT_EIGHT
#undef E64M4_OUTPUT_STORE
#endif
