#ifndef E64_M4_FP_PERIOD_PROPOSAL_H
#define E64_M4_FP_PERIOD_PROPOSAL_H

#include <stdint.h>

/* Source proposal only. Neither compiled nor substituted into any ELF. */
static inline __attribute__((always_inline)) void
e64_m4_store(uint64_t *destination, uint64_t value) {
    __builtin_memcpy(destination, &value, sizeof(value));
    __asm__ volatile("" ::: "memory");
}

#define E64_M4_PAIR(base, index, x, y) do { \
    e64_m4_store(a + (base) + (index), (x)); \
    e64_m4_store(b + (base) + (index), (y)); \
} while (0)

#define E64_M4_PERIOD(base, p0, p1, p2, p3, p4, p5, p6, p7) do { \
    E64_M4_PAIR(base, 0, p0, p0); \
    E64_M4_PAIR(base, 1, p1, p3); \
    E64_M4_PAIR(base, 2, p2, p6); \
    E64_M4_PAIR(base, 3, p3, p1); \
    E64_M4_PAIR(base, 4, p4, p4); \
    E64_M4_PAIR(base, 5, p5, p7); \
    E64_M4_PAIR(base, 6, p6, p2); \
    E64_M4_PAIR(base, 7, p7, p5); \
} while (0)

#define E64_M4_FULL(p0, p1, p2, p3, p4, p5, p6, p7) do { \
    E64_M4_PERIOD(0, p0, p1, p2, p3, p4, p5, p6, p7); \
    E64_M4_PERIOD(8, p0, p1, p2, p3, p4, p5, p6, p7); \
    E64_M4_PERIOD(16, p0, p1, p2, p3, p4, p5, p6, p7); \
    E64_M4_PERIOD(24, p0, p1, p2, p3, p4, p5, p6, p7); \
    E64_M4_PERIOD(32, p0, p1, p2, p3, p4, p5, p6, p7); \
    E64_M4_PERIOD(40, p0, p1, p2, p3, p4, p5, p6, p7); \
    E64_M4_PERIOD(48, p0, p1, p2, p3, p4, p5, p6, p7); \
    E64_M4_PERIOD(56, p0, p1, p2, p3, p4, p5, p6, p7); \
} while (0)

/* Requires the original disjoint a/b arrays (>=64 words), input8 table,
 * and seed0..2. Call INSIDE every original FP call, including VL0. */
static inline __attribute__((always_inline)) void
e64_m4_refresh_fp(uint64_t *a, uint64_t *b,
                  const volatile uint64_t *input8, unsigned seed) {
    const uint64_t t0 = input8[0];
    const uint64_t t1 = input8[1];
    const uint64_t t2 = input8[2];
    const uint64_t t3 = input8[3];
    const uint64_t t4 = input8[4];
    const uint64_t t5 = input8[5];
    const uint64_t t6 = input8[6];
    const uint64_t t7 = input8[7];
    switch (seed) {
    case 0: E64_M4_FULL(t0, t1, t2, t3, t4, t5, t6, t7); break;
    case 1: E64_M4_FULL(t1, t2, t3, t4, t5, t6, t7, t0); break;
    case 2: E64_M4_FULL(t2, t3, t4, t5, t6, t7, t0, t1); break;
    default: __builtin_trap();
    }
}

#undef E64_M4_FULL
#undef E64_M4_PERIOD
#undef E64_M4_PAIR
#endif
