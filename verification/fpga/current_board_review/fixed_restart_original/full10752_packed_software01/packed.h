#ifndef FIXED10752_PACKED_H
#define FIXED10752_PACKED_H

#include <stdint.h>
#include "expected.h"

#if SEW != 8 || INPUT_SEEDS != 3 || ACCUMULATOR_TRIALS != 1
#error "This port is only the original full e8/m4 three-seed parent"
#endif
#if !defined(FRACTIONAL_SUITE) || !INTEGER_EXTENSION || AGNOSTIC_POLICY
#error "Wrong fixed-point source configuration"
#endif
#if defined(FIXED_SCALAR_SUITE) || defined(INTEGER_SCALAR_SUITE) || defined(MACC_ACCUMULATORS)
#error "Different original parent"
#endif
#if UNMASKED_SUITE || CARRY_INPUT_SUITE || OPERATION_COUNT != 4
#error "Wrong predicate/operator contract"
#endif
#if defined(TRACE_OP0) || !defined(TRACE_RESTART_BOUNDARIES) || !defined(RESTART_SUITE)
#error "Keep the original restart order and exactly28 boundary records"
#endif
#if defined(__riscv) && __riscv_xlen != 64
#error "RV64 required"
#endif
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Packed byte oracle requires the original little-endian layout"
#endif
_Static_assert(sizeof(word) == 1 && sizeof(unsigned long) == 8, "Original RV64 ABI");

#define FIXED_INLINE static inline __attribute__((always_inline))

/* Compiler barriers retain source writes; these emit no hardware fence. */
FIXED_INLINE void fixed_store8(uint8_t *p, uint8_t value) {
    __builtin_memcpy(p, &value, 1);
    __asm__ volatile ("" ::: "memory");
}
FIXED_INLINE void fixed_store64(uint8_t *p, uint64_t value) {
    __builtin_memcpy(p, &value, 8);
    __asm__ volatile ("" ::: "memory");
}
FIXED_INLINE void fixed_store16(uint8_t *p, uint16_t value) {
    __builtin_memcpy(p, &value, 2);
    __asm__ volatile ("" ::: "memory");
}
FIXED_INLINE uint64_t fixed_actual64(const uint8_t *p) {
    uint64_t value;
    __builtin_memcpy(&value, p, 8);
    __asm__ volatile ("" : "+r" (value) : : "memory");
    return value;
}
FIXED_INLINE uint64_t fixed_actual16(const uint8_t *p) {
    uint16_t value;
    __builtin_memcpy(&value, p, 2);
    __asm__ volatile ("" : "+r" (value) : : "memory");
    return value;
}

/* bad is sticky, but never controls whether a subsequent actual load occurs. */
FIXED_INLINE unsigned fixed_compare(unsigned bad, uint64_t actual, uint64_t wanted) {
#if defined(__riscv)
    __asm__ volatile (
        "beq %[actual], %[wanted], 1f\n\t"
        "li %[bad], 1\n\t"
        "1:\n\t"
        : [bad] "+r" (bad)
        : [actual] "r" (actual), [wanted] "r" (wanted)
        : "memory");
#else
    if (actual != wanted) bad = 1;
#endif
    return bad;
}

#define FIXED_WORDS8(M, B) \
    M((B)+0) M((B)+8) M((B)+16) M((B)+24) \
    M((B)+32) M((B)+40) M((B)+48) M((B)+56)
#define FIXED_WORDS64(M) \
    FIXED_WORDS8(M, 0) FIXED_WORDS8(M, 64) \
    FIXED_WORDS8(M, 128) FIXED_WORDS8(M, 192) \
    FIXED_WORDS8(M, 256) FIXED_WORDS8(M, 320) \
    FIXED_WORDS8(M, 384) FIXED_WORDS8(M, 448)

FIXED_INLINE void fixed_initialize(uint8_t *p) {
#define FIXED_INIT(O) fixed_store64(p+(O), UINT64_C(0x5b5b5b5b5b5b5b5b));
    FIXED_WORDS64(FIXED_INIT)
#undef FIXED_INIT
    fixed_store16(p+512, UINT16_C(0x5b5b));
}

FIXED_INLINE unsigned fixed_compare_block(unsigned bad, const uint8_t *p, unsigned id) {
    if (id == FIXED_SENTINEL_BLOCK) {
#define FIXED_SENTINEL(O) bad = fixed_compare(bad, fixed_actual64(p+(O)), UINT64_C(0x5b5b5b5b5b5b5b5b));
        FIXED_WORDS8(FIXED_SENTINEL, 0)
#undef FIXED_SENTINEL
    } else {
        const uint64_t *gold = fixed_expected_blocks[id];
#define FIXED_GOLD(O) bad = fixed_compare(bad, fixed_actual64(p+(O)), gold[(O)/8]);
        FIXED_WORDS8(FIXED_GOLD, 0)
#undef FIXED_GOLD
    }
    return bad;
}

FIXED_INLINE unsigned fixed_mismatch(unsigned call, const uint8_t *p) {
    unsigned bad = 0;
    unsigned row = fixed_expected_index[call];
    if (row == 0) {
#define FIXED_SENTINEL(O) bad = fixed_compare(bad, fixed_actual64(p+(O)), UINT64_C(0x5b5b5b5b5b5b5b5b));
        FIXED_WORDS64(FIXED_SENTINEL)
#undef FIXED_SENTINEL
        bad = fixed_compare(bad, fixed_actual16(p+512), UINT64_C(0x5b5b));
    } else {
        const uint16_t *ids = fixed_expected_rows[row];
        bad = fixed_compare_block(bad, p+0, ids[0]);
        bad = fixed_compare_block(bad, p+64, ids[1]);
        bad = fixed_compare_block(bad, p+128, ids[2]);
        bad = fixed_compare_block(bad, p+192, ids[3]);
        bad = fixed_compare_block(bad, p+256, ids[4]);
        bad = fixed_compare_block(bad, p+320, ids[5]);
        bad = fixed_compare_block(bad, p+384, ids[6]);
        bad = fixed_compare_block(bad, p+448, ids[7]);
        unsigned tail = ids[8];
        uint64_t wanted = tail == FIXED_SENTINEL_TAIL ? UINT64_C(0x5b5b) :
                          (uint16_t)fixed_expected_blocks[tail][0];
        bad = fixed_compare(bad, fixed_actual16(p+512), wanted);
    }
    return bad;
}

#include "mask_stores.h"
#endif
