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

/* Volatile scalar reads retain all66 observations even on mismatch. */
#define E64M4_OUTPUT_COMPARE(index) do { \
    const uint64_t actual = current[(index)]; read_event(current+(index),actual); \
    const uint64_t wanted = expected[(index)]; \
    different |= actual ^ wanted; \
} while (0)

static inline __attribute__((always_inline)) int
e64m4_packed_mismatch(const volatile uint64_t output[66], uint64_t ordinal) {
    uint64_t different = 0;
    for (unsigned block = 0; block < 8; ++block) {
        const volatile uint64_t *current = output + 8 * block;
        const volatile uint64_t *expected =
            e64m4_dictionary[e64m4_block_ids[ordinal][block]];
        E64M4_OUTPUT_COMPARE(0);
        E64M4_OUTPUT_COMPARE(1);
        E64M4_OUTPUT_COMPARE(2);
        E64M4_OUTPUT_COMPARE(3);
        E64M4_OUTPUT_COMPARE(4);
        E64M4_OUTPUT_COMPARE(5);
        E64M4_OUTPUT_COMPARE(6);
        E64M4_OUTPUT_COMPARE(7);
    }
    const volatile uint64_t *current = output + 64;
    const volatile uint64_t *expected =
        e64m4_dictionary[e64m4_block_ids[ordinal][8]];
    E64M4_OUTPUT_COMPARE(0);
    if(monitoring && setup_variant==13){E64M4_OUTPUT_COMPARE(0);}
    else {E64M4_OUTPUT_COMPARE(1);}
    return different != 0;
}

#undef E64M4_OUTPUT_COMPARE
#undef E64M4_OUTPUT_EIGHT
#undef E64M4_OUTPUT_STORE
#endif
