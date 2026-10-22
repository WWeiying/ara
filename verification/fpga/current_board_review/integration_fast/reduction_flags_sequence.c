#include <stdint.h>

extern void replay_text(const char *);
extern int replay_mismatch(unsigned long, unsigned long, unsigned long, unsigned long);
extern unsigned long m8widen_op_0(const void *, const void *, void *, unsigned long,
                                unsigned long, const void *, unsigned long);
extern unsigned long m8widen_op_1(const void *, const void *, void *, unsigned long,
                                unsigned long, const void *, unsigned long);

int extension_main(void) {
    static uint32_t source[256] __attribute__((aligned(64)));
    static uint64_t seed[16] __attribute__((aligned(64)));
    static uint64_t output[18] __attribute__((aligned(64)));
    static uint8_t mask[32] __attribute__((aligned(64)));
    for (unsigned trial = 0; trial < 8; ++trial) {
        for (unsigned i = 0; i < 256; ++i) source[i] = 0x40000000;
        for (unsigned i = 0; i < 16; ++i) seed[i] = 0x5b;
        for (unsigned i = 0; i < 18; ++i) output[i] = 0x5b;
        for (unsigned i = 0; i < 32; ++i) mask[i] = 0;
        seed[0] = UINT64_C(0x4000000000000000);
        uint64_t expected = UINT64_C(0x7ff8000000000000);
        unsigned flags = 16;
        if (trial == 0 || trial == 5) {
            source[1] = 0x7f800000;
            source[33] = 0xff800000;
            mask[0] = mask[4] = 2;
        } else if (trial == 1 || trial == 4 || trial == 6) {
            seed[0] = trial == 6 ? UINT64_C(0x4000000000000000)
                      : trial == 4 ? UINT64_C(0x7ff8000000001234)
                                 : UINT64_C(0x7ff0000000000001);
            expected = seed[0];
            flags = 0;
        } else if (trial == 3) {
            seed[0] = UINT64_C(0x7ff0000000000001);
            mask[0] = 2;
        } else {
            for (unsigned i = 0; i < 32; ++i) mask[i] = 255;
            expected = UINT64_C(0x4060800000000000); /* 2 + 65 * 2 = 132. */
            flags = 0;
        }
        unsigned long prior = trial & 1;
        __asm__ volatile("csrw fflags,%0" :: "r"(prior) : "memory");
        /* Ordered sums require exact inactive NaN seed preservation. Unordered
         * sums permit canonicalization, so trial 6 uses a finite inactive seed. */
        unsigned long status = (trial == 1 || trial == 4 || trial == 7
                                ? m8widen_op_0 : m8widen_op_1)(
            source, seed, output + 1, 65, 256, mask, 0);
        unsigned long restored;
        __asm__ volatile("fence; csrr zero,vl; csrr %0,fflags"
                         : "=r"(restored) :: "memory");
        if ((uint32_t)status) return replay_mismatch(trial, ~0UL, 0, (uint32_t)status);
        if (output[1] != expected) return replay_mismatch(trial, 1, expected, output[1]);
        if (status >> 32 != flags) return replay_mismatch(trial, ~1UL, flags, status >> 32);
        if (restored != prior) return replay_mismatch(trial, ~2UL, prior, restored);
        for (unsigned i = 0; i < 18; ++i)
            if (i != 1 && output[i] != 0x5b) return replay_mismatch(trial, i, 0x5b, output[i]);

        /* The ordinary path must keep reporting exceptions after each tree,
         * and a subsequent clear/finite operation must not replay old NV. */
        uint32_t a = trial & 1 ? 0x3f800000 : 0x7f800001;
        uint32_t b = 0x3f800000, result = 0;
        unsigned long ordinary_flags;
        __asm__ volatile(
            "vsetivli zero,1,e32,m1,tu,mu\n"
            "vle32.v v4,(%1)\nvle32.v v5,(%2)\ncsrwi fflags,0\n"
            "vfadd.vv v6,v4,v5\ncsrr %0,fflags\nvse32.v v6,(%3)\n"
            "fence\ncsrr zero,vl\n"
            : "=&r"(ordinary_flags) : "r"(&a), "r"(&b), "r"(&result)
            : "memory");
        uint32_t ordinary_expected = trial & 1 ? 0x40000000 : 0x7fc00000;
        unsigned expected_flags = trial & 1 ? 0 : 16;
        if (result != ordinary_expected) return replay_mismatch(trial, 32, ordinary_expected, result);
        if (ordinary_flags != expected_flags) return replay_mismatch(trial, 33, expected_flags, ordinary_flags);
    }
    replay_text("EXTENDED_PASS flags_sequence reductions=8 ordinary=8\n");
    return 0;
}
