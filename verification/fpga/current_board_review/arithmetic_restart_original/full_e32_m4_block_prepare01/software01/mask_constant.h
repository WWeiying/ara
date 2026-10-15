#ifndef E32_M4_MASK_CONSTANT_SOURCE_PROPOSAL01_H
#define E32_M4_MASK_CONSTANT_SOURCE_PROPOSAL01_H

#include <stdint.h>

/* Source proposal only. Caller must first verify actual e32/m4 capacity128. */
#define E32M4_MASK_SB(OFFSET, VALUE) do { \
    bytes[(OFFSET)] = (uint8_t)(VALUE); \
    __asm__ volatile ("" ::: "memory"); \
} while (0)

#define E32M4_MASK_ALL_BYTE(OFFSET) do { \
    E32M4_MASK_SB(OFFSET, 1); \
    E32M4_MASK_SB(OFFSET, 3); \
    E32M4_MASK_SB(OFFSET, 7); \
    E32M4_MASK_SB(OFFSET, 15); \
    E32M4_MASK_SB(OFFSET, 31); \
    E32M4_MASK_SB(OFFSET, 63); \
    E32M4_MASK_SB(OFFSET, 127); \
    E32M4_MASK_SB(OFFSET, 255); \
} while (0)

#define E32M4_MASK_ODD_BYTE(OFFSET) do { \
    E32M4_MASK_SB(OFFSET, 2); \
    E32M4_MASK_SB(OFFSET, 10); \
    E32M4_MASK_SB(OFFSET, 42); \
    E32M4_MASK_SB(OFFSET, 170); \
} while (0)

#define E32M4_MASK_ZERO8(OFFSET) do { \
    __builtin_memcpy(mask + (OFFSET), &zero, 8); \
    __asm__ volatile ("" ::: "memory"); \
} while (0)

/* No reads from mask are needed: clear precedes every ordered constant SB. */
static __attribute__((noinline)) void
e32m4_initialize_mask_128(uint8_t mask[128], unsigned mode)
{
    const uint64_t zero = UINT64_C(0);
    volatile uint8_t *const bytes = mask;

    E32M4_MASK_ZERO8(0);
    E32M4_MASK_ZERO8(8);
    E32M4_MASK_ZERO8(16);
    E32M4_MASK_ZERO8(24);
    E32M4_MASK_ZERO8(32);
    E32M4_MASK_ZERO8(40);
    E32M4_MASK_ZERO8(48);
    E32M4_MASK_ZERO8(56);
    E32M4_MASK_ZERO8(64);
    E32M4_MASK_ZERO8(72);
    E32M4_MASK_ZERO8(80);
    E32M4_MASK_ZERO8(88);
    E32M4_MASK_ZERO8(96);
    E32M4_MASK_ZERO8(104);
    E32M4_MASK_ZERO8(112);
    E32M4_MASK_ZERO8(120);

    switch (mode) {
    case 0:
        E32M4_MASK_ALL_BYTE(0);
        E32M4_MASK_ALL_BYTE(1);
        E32M4_MASK_ALL_BYTE(2);
        E32M4_MASK_ALL_BYTE(3);
        E32M4_MASK_ALL_BYTE(4);
        E32M4_MASK_ALL_BYTE(5);
        E32M4_MASK_ALL_BYTE(6);
        E32M4_MASK_ALL_BYTE(7);
        E32M4_MASK_ALL_BYTE(8);
        E32M4_MASK_ALL_BYTE(9);
        E32M4_MASK_ALL_BYTE(10);
        E32M4_MASK_ALL_BYTE(11);
        E32M4_MASK_ALL_BYTE(12);
        E32M4_MASK_ALL_BYTE(13);
        E32M4_MASK_ALL_BYTE(14);
        E32M4_MASK_ALL_BYTE(15);
        break;
    case 1:
        E32M4_MASK_ODD_BYTE(0);
        E32M4_MASK_ODD_BYTE(1);
        E32M4_MASK_ODD_BYTE(2);
        E32M4_MASK_ODD_BYTE(3);
        E32M4_MASK_ODD_BYTE(4);
        E32M4_MASK_ODD_BYTE(5);
        E32M4_MASK_ODD_BYTE(6);
        E32M4_MASK_ODD_BYTE(7);
        E32M4_MASK_ODD_BYTE(8);
        E32M4_MASK_ODD_BYTE(9);
        E32M4_MASK_ODD_BYTE(10);
        E32M4_MASK_ODD_BYTE(11);
        E32M4_MASK_ODD_BYTE(12);
        E32M4_MASK_ODD_BYTE(13);
        E32M4_MASK_ODD_BYTE(14);
        E32M4_MASK_ODD_BYTE(15);
        break;
    case 2:
        /* Original selected indices: 2,9,16,23,...,121. */
        E32M4_MASK_SB(0, 4);
        E32M4_MASK_SB(1, 2);
        E32M4_MASK_SB(2, 1);
        E32M4_MASK_SB(2, 129);
        E32M4_MASK_SB(3, 64);
        E32M4_MASK_SB(4, 32);
        E32M4_MASK_SB(5, 16);
        E32M4_MASK_SB(6, 8);
        E32M4_MASK_SB(7, 4);
        E32M4_MASK_SB(8, 2);
        E32M4_MASK_SB(9, 1);
        E32M4_MASK_SB(9, 129);
        E32M4_MASK_SB(10, 64);
        E32M4_MASK_SB(11, 32);
        E32M4_MASK_SB(12, 16);
        E32M4_MASK_SB(13, 8);
        E32M4_MASK_SB(14, 4);
        E32M4_MASK_SB(15, 2);
        break;
    default:
        /* Not a source tuple; do not silently accept a different mode. */
        __builtin_trap();
    }
}

#undef E32M4_MASK_ZERO8
#undef E32M4_MASK_ODD_BYTE
#undef E32M4_MASK_ALL_BYTE
#undef E32M4_MASK_SB

#endif
