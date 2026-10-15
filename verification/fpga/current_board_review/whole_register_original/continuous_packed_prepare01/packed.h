#ifndef WHOLE_PACKED_H
#define WHOLE_PACKED_H
#include <stdint.h>
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This source port requires the actual little-endian target byte order
#endif
#include "input_table.h"

static inline uint64_t packed_load(const uint8_t *p) {
    uint64_t value;
    __builtin_memcpy(&value, __builtin_assume_aligned(p, 8), 8);
    return value;
}

static inline void packed_store(uint8_t *p, uint64_t value) {
    __builtin_memcpy(__builtin_assume_aligned(p, 8), &value, 8);
}

static inline void packed_init(uint8_t *in, uint8_t *out, unsigned seed) {
    for (unsigned i = 0; i < 128; ++i)
        packed_store(in + i * 8, input_table[seed][i % 32]);
    for (unsigned i = 0; i < 136; ++i)
        packed_store(out + i * 8, UINT64_C(0x5b5b5b5b5b5b5b5b));
}

static inline uint64_t packed_expected(const uint8_t *in, unsigned offset,
                                      unsigned lo, unsigned hi) {
    const uint64_t sentinel = UINT64_C(0x5b5b5b5b5b5b5b5b);
    if (offset + 8 <= lo || offset >= hi || lo == hi)
        return sentinel;
    /* Only middle words overlap the original [32,1056) active region. */
    uint64_t value = packed_load(in + offset - 32);
    uint64_t mask = UINT64_MAX;
    if (lo > offset)
        mask &= UINT64_MAX << ((lo - offset) * 8);
    if (hi < offset + 8)
        mask &= UINT64_MAX >> ((offset + 8 - hi) * 8);
    return (value & mask) | (sentinel & ~mask);
}
#endif
