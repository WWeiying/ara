#ifndef UNBOXED_FULL17920_PACKED_CORE_H
#define UNBOXED_FULL17920_PACKED_CORE_H
#include <stdint.h>

/* Scalar asm makes the required fresh stores explicit without type punning.
 * Offsets are bytes; arrays are aligned to eight bytes. No vector/FP/CSR ops. */
#define SD_AT(base, offset, value) \
    __asm__ volatile("sd %0,%c1(%2)" : : "r"((uint64_t)(value)), \
                     "i"(offset), "r"(base) : "memory")
#define SH_AT(base, offset, value) \
    __asm__ volatile("sh %0,%c1(%2)" : : "r"((uint64_t)(value)), \
                     "i"(offset), "r"(base) : "memory")
#define ALL_16_SD(base, value) do { \
    SD_AT(base, 0, value); SD_AT(base, 8, value); \
    SD_AT(base, 16, value); SD_AT(base, 24, value); \
    SD_AT(base, 32, value); SD_AT(base, 40, value); \
    SD_AT(base, 48, value); SD_AT(base, 56, value); \
    SD_AT(base, 64, value); SD_AT(base, 72, value); \
    SD_AT(base, 80, value); SD_AT(base, 88, value); \
    SD_AT(base, 96, value); SD_AT(base, 104, value); \
    SD_AT(base, 112, value); SD_AT(base, 120, value); \
} while (0)

static inline void fresh_inputs(void *a, void *b,
                                const uint64_t *ar, const uint64_t *br) {
    SD_AT(a, 0, ar[0]); SD_AT(b, 0, br[0]);
    SD_AT(a, 8, ar[1]); SD_AT(b, 8, br[1]);
    SD_AT(a, 16, ar[2]); SD_AT(b, 16, br[2]);
    SD_AT(a, 24, ar[3]); SD_AT(b, 24, br[3]);
}

static inline uint32_t result_and_guards(const void *output) {
    unsigned long value;
    __asm__ volatile("lwu %0,0(%1)" : "=r"(value) : "r"(output) : "memory");
    return (uint32_t)value;
}

static inline unsigned packed_errors(uint32_t actual, uint64_t status,
                                     uint64_t record, unsigned flags) {
    unsigned result = (actual >> 8) & 65535U;
    unsigned bad = (result & (unsigned)(record & 65535U)) |
                   ((~result & 65535U) & (unsigned)((record >> 16) & 65535U));
    unsigned errors = (uint32_t)status != 0;
    /* Count every wrong result bit; two equal errors cannot cancel. */
    while (bad) { ++errors; bad &= bad - 1; }
    errors += (status >> 32) != flags;
    errors += (actual & 255U) != 0x5b || (actual >> 24) != 0x5b;
    return errors;
}
#endif
