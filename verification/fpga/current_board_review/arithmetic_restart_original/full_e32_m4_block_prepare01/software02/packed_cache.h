#ifndef E32M4_INTEGRATED_PACKED_CACHE_H
#define E32M4_INTEGRATED_PACKED_CACHE_H
#include <stdint.h>

extern const uint64_t e32m4_expected_blocks[2252][8];
extern const uint16_t e32m4_expected_ids[5985][9];

/* The empty volatile asm consumes every real read, including after a mismatch. */
static __attribute__((always_inline)) inline uint64_t
e32m4_actual8(const unsigned char *p)
{
    uint64_t value;
    __builtin_memcpy(&value, p, 8);
    __asm__ volatile ("" : "+r"(value) : : "memory");
    return value;
}

static __attribute__((always_inline)) inline uint64_t
e32m4_gold8(const uint64_t *p)
{
    uint64_t value;
    __builtin_memcpy(&value, p, 8);
    return value;
}

static __attribute__((noinline)) void e32m4_initialize_output(void *out)
{
    const uint64_t sentinel = UINT64_C(0x0000005b0000005b);
    unsigned char *const p = out;
    __builtin_memcpy(p + 0, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 8, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 16, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 24, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 32, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 40, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 48, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 56, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 64, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 72, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 80, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 88, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 96, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 104, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 112, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 120, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 128, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 136, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 144, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 152, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 160, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 168, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 176, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 184, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 192, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 200, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 208, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 216, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 224, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 232, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 240, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 248, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 256, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 264, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 272, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 280, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 288, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 296, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 304, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 312, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 320, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 328, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 336, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 344, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 352, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 360, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 368, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 376, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 384, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 392, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 400, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 408, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 416, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 424, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 432, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 440, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 448, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 456, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 464, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 472, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 480, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 488, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 496, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 504, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
    __builtin_memcpy(p + 512, &sentinel, 8);
    __asm__ volatile ("" ::: "memory");
}

#define E32M4_CACHE_FILL(ID) do { \
    const uint64_t *const block = blocks[(ID)]; \
    c0 = e32m4_gold8(block + 0); \
    c1 = e32m4_gold8(block + 1); \
    c2 = e32m4_gold8(block + 2); \
    c3 = e32m4_gold8(block + 3); \
    c4 = e32m4_gold8(block + 4); \
    c5 = e32m4_gold8(block + 5); \
    c6 = e32m4_gold8(block + 6); \
    c7 = e32m4_gold8(block + 7); \
    tag = (ID); \
} while (0)

/* Same BEQ/LI sticky contract as the reviewed e64/m4 scalar comparator. */
#if defined(__riscv) && __riscv_xlen != 64
#error "This comparator requires RV64"
#endif

#if defined(__riscv)
#define E32M4_STICKY_UPDATE(ACTUAL_VALUE, WANTED_VALUE) do { \
    const uint64_t actual_value = (ACTUAL_VALUE); \
    const uint64_t wanted_value = (WANTED_VALUE); \
    __asm__ volatile( \
        "beq %[actual], %[wanted], 1f\n\t" \
        "li %[bad], 1\n\t" \
        "1:\n\t" \
        : [bad] "+r" (mismatch) \
        : [actual] "r" (actual_value), [wanted] "r" (wanted_value) \
        : "memory"); \
} while (0)
#else
#define E32M4_STICKY_UPDATE(ACTUAL_VALUE, WANTED_VALUE) do { \
    if ((ACTUAL_VALUE) != (WANTED_VALUE)) mismatch = 1; \
} while (0)
#endif

/* Each condition may latch failure, but none bypasses a later actual read. */
#define E32M4_COMPARE_BLOCK(OFFSET) do { \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 0), c0); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 8), c1); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 16), c2); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 24), c3); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 32), c4); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 40), c5); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 48), c6); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 56), c7); \
} while (0)

#define E32M4_NEXT_BLOCK(INDEX) do { \
    const uint16_t id = ids[(INDEX)]; \
    if (id != tag) E32M4_CACHE_FILL(id); \
    E32M4_COMPARE_BLOCK(64 * (INDEX)); \
} while (0)

static __attribute__((noinline)) unsigned
e32m4_packed_mismatch(const void *out, const uint16_t ids[9],
                      const uint64_t blocks[2252][8])
{
    const unsigned char *const p = out;
    uint64_t c0, c1, c2, c3, c4, c5, c6, c7;
    uint16_t tag;
    unsigned mismatch = 0;
    const uint16_t first_id = ids[0];

    /* Unconditional first fill invalidates any previous call's cache state. */
    E32M4_CACHE_FILL(first_id);
    E32M4_COMPARE_BLOCK(0);
    E32M4_NEXT_BLOCK(1);
    E32M4_NEXT_BLOCK(2);
    E32M4_NEXT_BLOCK(3);
    E32M4_NEXT_BLOCK(4);
    E32M4_NEXT_BLOCK(5);
    E32M4_NEXT_BLOCK(6);
    E32M4_NEXT_BLOCK(7);

    const uint16_t last_id = ids[8];
    const uint64_t last = e32m4_gold8(blocks[last_id]);
    E32M4_STICKY_UPDATE(e32m4_actual8(p + 512), last);
    return mismatch;
}

#undef E32M4_STICKY_UPDATE
#undef E32M4_NEXT_BLOCK
#undef E32M4_COMPARE_BLOCK
#undef E32M4_CACHE_FILL
#endif

