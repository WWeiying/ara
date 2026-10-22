static uint32_t a[1024],b[1024];
#ifndef E32M4_INTEGRATED_FP_PERIOD_H
#define E32M4_INTEGRATED_FP_PERIOD_H
#include <stdint.h>

/* Four-byte typed stores, each observable across a compiler barrier. */
static __attribute__((always_inline)) inline void
e32m4_fp_store(uint32_t *dst, uint32_t value)
{
    if(running && ((fault==20 && calls==1366 && dst==a+127)||(fault==21 && calls==1366 && dst==b+127)))return;
    if(running && fault==22 && dst==a)dst=b;
    __builtin_memcpy(dst, &value, 4); fp_event(dst,value);
    __asm__ volatile ("" ::: "memory");
}

#define E32M4_FP_PERIOD(BASE, A0, B0, A1, B1, A2, B2, A3, B3, A4, B4, A5, B5, A6, B6, A7, B7) do { \
    e32m4_fp_store(a + (BASE) + 0, (A0)); \
    e32m4_fp_store(b + (BASE) + 0, (B0)); \
    e32m4_fp_store(a + (BASE) + 1, (A1)); \
    e32m4_fp_store(b + (BASE) + 1, (B1)); \
    e32m4_fp_store(a + (BASE) + 2, (A2)); \
    e32m4_fp_store(b + (BASE) + 2, (B2)); \
    e32m4_fp_store(a + (BASE) + 3, (A3)); \
    e32m4_fp_store(b + (BASE) + 3, (B3)); \
    e32m4_fp_store(a + (BASE) + 4, (A4)); \
    e32m4_fp_store(b + (BASE) + 4, (B4)); \
    e32m4_fp_store(a + (BASE) + 5, (A5)); \
    e32m4_fp_store(b + (BASE) + 5, (B5)); \
    e32m4_fp_store(a + (BASE) + 6, (A6)); \
    e32m4_fp_store(b + (BASE) + 6, (B6)); \
    e32m4_fp_store(a + (BASE) + 7, (A7)); \
    e32m4_fp_store(b + (BASE) + 7, (B7)); \
} while (0)

#define E32M4_FP_ALL(...) do { \
    E32M4_FP_PERIOD(0, __VA_ARGS__); \
    E32M4_FP_PERIOD(8, __VA_ARGS__); \
    E32M4_FP_PERIOD(16, __VA_ARGS__); \
    E32M4_FP_PERIOD(24, __VA_ARGS__); \
    E32M4_FP_PERIOD(32, __VA_ARGS__); \
    E32M4_FP_PERIOD(40, __VA_ARGS__); \
    E32M4_FP_PERIOD(48, __VA_ARGS__); \
    E32M4_FP_PERIOD(56, __VA_ARGS__); \
    E32M4_FP_PERIOD(64, __VA_ARGS__); \
    E32M4_FP_PERIOD(72, __VA_ARGS__); \
    E32M4_FP_PERIOD(80, __VA_ARGS__); \
    E32M4_FP_PERIOD(88, __VA_ARGS__); \
    E32M4_FP_PERIOD(96, __VA_ARGS__); \
    E32M4_FP_PERIOD(104, __VA_ARGS__); \
    E32M4_FP_PERIOD(112, __VA_ARGS__); \
    E32M4_FP_PERIOD(120, __VA_ARGS__); \
} while (0)

static __attribute__((noinline)) void
e32m4_refresh_fp(uint32_t *a, uint32_t *b, const uint32_t *input, unsigned seed)
{
    const volatile uint32_t *const table = input;
    const uint32_t v0 = table[0]; if(!(running && fault==34 && 0==7))input_event(0,v0);
    const uint32_t v1 = table[1]; if(!(running && fault==34 && 1==7))input_event(1,v1);
    const uint32_t v2 = table[2]; if(!(running && fault==34 && 2==7))input_event(2,v2);
    const uint32_t v3 = table[3]; if(!(running && fault==34 && 3==7))input_event(3,v3);
    const uint32_t v4 = table[4]; if(!(running && fault==34 && 4==7))input_event(4,v4);
    const uint32_t v5 = table[5]; if(!(running && fault==34 && 5==7))input_event(5,v5);
    const uint32_t v6 = table[6]; if(!(running && fault==34 && 6==7))input_event(6,v6);
    const uint32_t v7 = table[7]; if(!(running && fault==34 && 7==7))input_event(7,v7);
    switch (seed) {
    case 0:
        E32M4_FP_ALL(v0, v0, v1, v3, v2, v6, v3, v1, v4, v4, v5, v7, v6, v2, v7, v5);
        break;
    case 1:
        E32M4_FP_ALL(v1, v1, v2, v4, v3, v7, v4, v2, v5, v5, v6, v0, v7, v3, v0, v6);
        break;
    case 2:
        E32M4_FP_ALL(v2, v2, v3, v5, v4, v0, v5, v3, v6, v6, v7, v1, v0, v4, v1, v7);
        break;
    default:
        __builtin_trap();
    }
}

#undef E32M4_FP_ALL
#undef E32M4_FP_PERIOD
#endif
