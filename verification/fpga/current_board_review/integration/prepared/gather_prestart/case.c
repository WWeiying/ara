/* Handoff02 CASE4 generic gather; board_tested=false, not verified03 original. */
#if CASE != 4
#error Only the nonfault gather case is ported
#endif
#include <stdint.h>

static uint8_t input[4096] __attribute__((aligned(64)));
static uint8_t second[4096] __attribute__((aligned(64)));
static uint8_t output[4096] __attribute__((aligned(64)));
static uint8_t expected[4096] __attribute__((aligned(64)));
static uint8_t mask[128] __attribute__((aligned(64)));
static uint64_t state[3];
extern void run_case(const void *, const void *, void *, const void *, unsigned long, void *);

extern long replay_write(long,long,long,long);
static void text(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    replay_write(64, 1, (long)s, n);
}
static void number(uint64_t x) {
    char buf[24]; unsigned n = 23; buf[n] = 0;
    do { buf[--n] = '0' + x % 10; x /= 10; } while (x);
    text(buf + n);
}
int gather_prestart_main(void) {
    unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
    if (vlenb != 128) { text("RVV_REPRO_REQUIRES_VLEN1024\n"); return 77; }
    unsigned bytes = vlenb, errors = 0;
    const void *source = input;
    for (unsigned i = 0; i < sizeof(input); ++i) {
        input[i] = (uint8_t)(17 + i); second[i] = 0x3c;
        output[i] = expected[i] = 0x5b;
    }
    for (unsigned i = 0; i < sizeof(mask); ++i) mask[i] = 255;
#if CASE == 1
    for (unsigned i = 2; i < bytes; ++i) expected[i] = input[i];
#elif CASE == 2
    ((uint32_t *)input)[0] = 0x3f800000; /* 1.0f */
    ((uint64_t *)second)[0] = UINT64_C(0x4000000000000000); /* 2.0 */
    ((uint64_t *)expected)[0] = UINT64_C(0x4008000000000000); /* 3.0 */
    bytes = 8;
#elif CASE == 3
    bytes = 512;
    for (unsigned i = 256; i < bytes; ++i) expected[i] = input[i] ^ second[i];
#elif CASE == 4 || CASE == 5 || CASE == 6 || CASE == 12
    for (unsigned i = 0; i < vlenb / 2; ++i) {
        ((uint16_t *)input)[i] = (uint16_t)(1000 + i);
        ((uint16_t *)output)[i] = ((uint16_t *)expected)[i] = 91;
    }
    ((uint16_t *)expected)[1] = CASE == 6 ? 0 : CASE == 12 ? 1001 : 1000;
#elif CASE == 7
    for (unsigned i = 0; i < vlenb / 4; ++i) {
        ((uint32_t *)input)[i] = 0; ((uint32_t *)second)[i] = 0;
    }
    ((uint32_t *)input)[0] = 0x7f800001; /* Masked signaling NaN. */
    for (unsigned i = 0; i < sizeof(mask); ++i) mask[i] = 0;
    bytes = 0; /* Mask-result tail bits are architecturally agnostic. */
#elif CASE == 8 || CASE == 9
    long mapping = syscall6(222, 0, 8192, 3, 0x22, -1, 0);
    if ((unsigned long)mapping >= (unsigned long)-4095L) {
        text("RVV_REPRO_SETUP_MMAP_FAILED\n"); return 2;
    }
    if (syscall6(226, mapping + 4096, 4096, 0, 0, 0, 0)) {
        text("RVV_REPRO_SETUP_MPROTECT_FAILED\n"); return 2;
    }
    if (CASE == 8) {
        source = (const void *)(mapping + 4096);
        for (unsigned i = 0; i < sizeof(mask); ++i) mask[i] = 0;
    } else {
        source = (const void *)(mapping + 4092);
        for (unsigned i = 0; i < 4; ++i) {
            ((uint8_t *)mapping)[4092 + i] = i + 1; expected[i] = i + 1;
        }
        bytes = 4; /* FOF may modify elements after the shortened VL. */
    }
#elif CASE == 10
    bytes = 4;
    ((uint16_t *)expected)[0] = input[0];
    ((uint16_t *)expected)[1] = input[1];
#elif CASE == 11
    bytes = 512; expected[511] = input[0];
#endif
    text("RVV_REPRO_BEGIN case="); number(CASE); text("\n");
    run_case(source, second, output, mask, vlenb, state);
    text("RVV_REPRO_RETURNED vstart="); number(state[0]);
    text(" fflags="); number(state[1]); text(" vl="); number(state[2]); text("\n");
    if (state[0]) ++errors;
#if CASE == 2 || CASE == 7
    if (state[1]) ++errors;
#endif
#if CASE == 7
    if ((output[0] & 15) != (expected[0] & 15)) ++errors;
#endif
#if CASE == 9
    if (state[2] != 4) ++errors;
#endif
    for (unsigned i = 0; i < bytes; ++i) if (output[i] != expected[i]) {
        if (errors < 8) {
            text("RVV_REPRO_MISMATCH byte="); number(i);
            text(" expected="); number(expected[i]); text(" actual="); number(output[i]); text("\n");
        }
        ++errors;
    }
    text(errors ? "RVV_REPRO_FAIL errors=" : "RVV_REPRO_PASS errors=");
    number(errors); text("\n"); return errors ? 1 : 0;
}

