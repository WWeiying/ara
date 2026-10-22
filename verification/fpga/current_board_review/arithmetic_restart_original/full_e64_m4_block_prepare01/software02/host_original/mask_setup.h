#ifndef E64_M4_MASK_SETUP_H
#define E64_M4_MASK_SETUP_H
#include <stdint.h>

/* CAP64 only. No final-mask copy: every original selected byte RMW remains. */
#define E64M4_MASK_BARRIER() __asm__ volatile("" ::: "memory")
#define E64M4_MASK_CLEAR(offset) do { \
    if(!skip_clear(offset)){__builtin_memcpy(mask + (offset), &zero, 8); mask_event(0,(offset),mask);} \
    E64M4_MASK_BARRIER(); \
} while (0)
#define E64M4_MASK_BIT(index) do { \
    if(!skip_bit(index)){ \
    mask[(index) / 8u] = (uint8_t)(mask[(index) / 8u] | \
                                (UINT32_C(1) << ((index) % 8u))); \
    mask_event(1,(index),mask); } \
    E64M4_MASK_BARRIER(); \
} while (0)

static inline __attribute__((always_inline)) void
e64m4_initialize_mask(uint8_t mask[128], unsigned mode) {
    const uint64_t zero = 0;
    E64M4_MASK_CLEAR(0);
    E64M4_MASK_CLEAR(8);
    E64M4_MASK_CLEAR(16);
    E64M4_MASK_CLEAR(24);
    E64M4_MASK_CLEAR(32);
    E64M4_MASK_CLEAR(40);
    E64M4_MASK_CLEAR(48);
    E64M4_MASK_CLEAR(56);
    E64M4_MASK_CLEAR(64);
    E64M4_MASK_CLEAR(72);
    E64M4_MASK_CLEAR(80);
    E64M4_MASK_CLEAR(88);
    E64M4_MASK_CLEAR(96);
    E64M4_MASK_CLEAR(104);
    E64M4_MASK_CLEAR(112);
    E64M4_MASK_CLEAR(120);
    if (mode == 0) {
        if(monitoring && setup_variant==9 && calls==0){E64M4_MASK_BIT(1);E64M4_MASK_BIT(0);}
        else{E64M4_MASK_BIT(0);E64M4_MASK_BIT(1);}
        E64M4_MASK_BIT(2);
        E64M4_MASK_BIT(3);
        E64M4_MASK_BIT(4);
        E64M4_MASK_BIT(5);
        E64M4_MASK_BIT(6);
        E64M4_MASK_BIT(7);
        E64M4_MASK_BIT(8);
        E64M4_MASK_BIT(9);
        E64M4_MASK_BIT(10);
        E64M4_MASK_BIT(11);
        E64M4_MASK_BIT(12);
        E64M4_MASK_BIT(13);
        E64M4_MASK_BIT(14);
        E64M4_MASK_BIT(15);
        E64M4_MASK_BIT(16);
        E64M4_MASK_BIT(17);
        E64M4_MASK_BIT(18);
        E64M4_MASK_BIT(19);
        E64M4_MASK_BIT(20);
        E64M4_MASK_BIT(21);
        E64M4_MASK_BIT(22);
        E64M4_MASK_BIT(23);
        E64M4_MASK_BIT(24);
        E64M4_MASK_BIT(25);
        E64M4_MASK_BIT(26);
        E64M4_MASK_BIT(27);
        E64M4_MASK_BIT(28);
        E64M4_MASK_BIT(29);
        E64M4_MASK_BIT(30);
        E64M4_MASK_BIT(31);
        E64M4_MASK_BIT(32);
        E64M4_MASK_BIT(33);
        E64M4_MASK_BIT(34);
        E64M4_MASK_BIT(35);
        E64M4_MASK_BIT(36);
        E64M4_MASK_BIT(37);
        E64M4_MASK_BIT(38);
        E64M4_MASK_BIT(39);
        E64M4_MASK_BIT(40);
        E64M4_MASK_BIT(41);
        E64M4_MASK_BIT(42);
        E64M4_MASK_BIT(43);
        E64M4_MASK_BIT(44);
        E64M4_MASK_BIT(45);
        E64M4_MASK_BIT(46);
        E64M4_MASK_BIT(47);
        E64M4_MASK_BIT(48);
        E64M4_MASK_BIT(49);
        E64M4_MASK_BIT(50);
        E64M4_MASK_BIT(51);
        E64M4_MASK_BIT(52);
        E64M4_MASK_BIT(53);
        E64M4_MASK_BIT(54);
        E64M4_MASK_BIT(55);
        E64M4_MASK_BIT(56);
        E64M4_MASK_BIT(57);
        E64M4_MASK_BIT(58);
        E64M4_MASK_BIT(59);
        E64M4_MASK_BIT(60);
        E64M4_MASK_BIT(61);
        E64M4_MASK_BIT(62);
        E64M4_MASK_BIT(63);
    } else if (mode == 1) {
        E64M4_MASK_BIT(1);
        E64M4_MASK_BIT(3);
        E64M4_MASK_BIT(5);
        E64M4_MASK_BIT(7);
        E64M4_MASK_BIT(9);
        E64M4_MASK_BIT(11);
        E64M4_MASK_BIT(13);
        E64M4_MASK_BIT(15);
        E64M4_MASK_BIT(17);
        E64M4_MASK_BIT(19);
        E64M4_MASK_BIT(21);
        E64M4_MASK_BIT(23);
        E64M4_MASK_BIT(25);
        E64M4_MASK_BIT(27);
        E64M4_MASK_BIT(29);
        E64M4_MASK_BIT(31);
        E64M4_MASK_BIT(33);
        E64M4_MASK_BIT(35);
        E64M4_MASK_BIT(37);
        E64M4_MASK_BIT(39);
        E64M4_MASK_BIT(41);
        E64M4_MASK_BIT(43);
        E64M4_MASK_BIT(45);
        E64M4_MASK_BIT(47);
        E64M4_MASK_BIT(49);
        E64M4_MASK_BIT(51);
        E64M4_MASK_BIT(53);
        E64M4_MASK_BIT(55);
        E64M4_MASK_BIT(57);
        E64M4_MASK_BIT(59);
        E64M4_MASK_BIT(61);
        E64M4_MASK_BIT(63);
    } else if (mode == 2) {
        E64M4_MASK_BIT(2);
        E64M4_MASK_BIT(9);
        E64M4_MASK_BIT(16);
        E64M4_MASK_BIT(23);
        E64M4_MASK_BIT(30);
        E64M4_MASK_BIT(37);
        E64M4_MASK_BIT(44);
        E64M4_MASK_BIT(51);
        E64M4_MASK_BIT(58);
    }
}

#undef E64M4_MASK_BIT
#undef E64M4_MASK_CLEAR
#undef E64M4_MASK_BARRIER
#endif
