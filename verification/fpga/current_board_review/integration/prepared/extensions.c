#include <stdint.h>

extern void replay_text(const char *);
extern int replay_mismatch(unsigned long, unsigned long, unsigned long, unsigned long);

#if REPLAY_EXT == 1 || REPLAY_EXT == 2
/* Source-origin integration check, not an original FPGA-case substitution.
 * e32 VL16/vstart8 and e64 VL8/vstart4 cross a four-lane aggregate.
 * A unique source per element distinguishes a skipped source prefix from a
 * merely corrected destination byte-enable. Include neighboring boundaries.
 */
#if REPLAY_EXT == 1
typedef uint32_t word;
#define SETUP "e32,m1,tu,mu\n"
#define LOAD "vle32.v "
#define STORE "vse32.v "
#define CAP 32
#define VL 16
#define BOUNDARY 8
#define MARKER "EXTENDED_PASS slide_source_e32 cases=8\n"
#else
typedef uint64_t word;
#define SETUP "e64,m1,tu,mu\n"
#define LOAD "vle64.v "
#define STORE "vse64.v "
#define CAP 16
#define VL 8
#define BOUNDARY 4
#define MARKER "EXTENDED_PASS slide_source_e64 cases=8\n"
#endif
int extension_main(void) {
    static word source[CAP] __attribute__((aligned(64)));
    static word destination[CAP] __attribute__((aligned(64)));
    static uint8_t mask[16] __attribute__((aligned(64)));
    const unsigned starts[] = {0, BOUNDARY - 1, BOUNDARY, BOUNDARY + 1};
    for (unsigned mode = 0; mode < 2; ++mode) {
        for (unsigned i = 0; i < sizeof(mask); ++i) mask[i] = mode ? 0x24 : 255;
        for (unsigned trial = 0; trial < 4; ++trial) {
            for (unsigned i = 0; i < CAP; ++i) { source[i] = 1000 + 37 * i; destination[i] = 91; }
            unsigned long returned, start = starts[trial], vl = VL;
            __asm__ volatile(
                "vsetvli t0,zero," SETUP
                LOAD "v8,(%1)\n" LOAD "v24,(%2)\n"
                "vlm.v v0,(%3)\n"
                "vsetvli t0,%4," SETUP
                "li t1,777\ncsrw vstart,%5\n"
                "vslide1up.vx v24,v8,t1,v0.t\ncsrr %0,vstart\n"
                "vsetvli t0,zero," SETUP STORE "v24,(%2)\nfence\ncsrr zero,vl\n"
                : "=&r"(returned) : "r"(source), "r"(destination), "r"(mask), "r"(vl), "r"(start)
                : "t0", "t1", "memory");
            if (returned) return replay_mismatch(4 * mode + trial, ~0UL, 0, returned);
            for (unsigned i = 0; i < CAP; ++i) {
                word expected = i >= start && i < VL && ((mask[i / 8] >> (i % 8)) & 1)
                                    ? (i ? source[i - 1] : 777) : 91;
                if (destination[i] != expected)
                    return replay_mismatch(4 * mode + trial, i, expected, destination[i]);
            }
        }
    }
    replay_text(MARKER);
    return 0;
}
#elif REPLAY_EXT == 3
extern unsigned long m8widen_op_0(const void *, const void *, void *, unsigned long,
                                  unsigned long, const void *, unsigned long);
extern unsigned long m8widen_op_1(const void *, const void *, void *, unsigned long,
                                  unsigned long, const void *, unsigned long);

/* All finite sums are exact integers in both FP32 and FP64. Build their IEEE
 * bits with integer arithmetic, not a floating/unsigned conversion oracle.
 */
static uint64_t integer_bits(unsigned n, unsigned mantissa, unsigned bias) {
    unsigned top = 0;
    for (unsigned x = n; x > 1; x >>= 1) ++top;
    return ((uint64_t)(top + bias) << mantissa) |
           ((uint64_t)(n - (1U << top)) << (mantissa - top));
}

int extension_main(void) {
    static uint32_t source[256] __attribute__((aligned(64)));
    static uint64_t seed[16] __attribute__((aligned(64)));
    static uint64_t output[18] __attribute__((aligned(64)));
    static uint8_t mask[32] __attribute__((aligned(64)));
    for (unsigned op = 0; op < 2; ++op) for (unsigned trial = 0; trial < 5; ++trial) {
        unsigned vl = trial < 2 ? 33 : 65;
        unsigned sparse = trial & 1, sum = 2;
        for (unsigned i = 0; i < 256; ++i) source[i] = integer_bits(1 + i % 7, 23, 127);
        for (unsigned i = 0; i < 16; ++i) seed[i] = 0x5b;
        seed[0] = integer_bits(2, 52, 1023);
        for (unsigned i = 0; i < 18; ++i) output[i] = 0x5b;
        for (unsigned i = 0; i < 32; ++i) mask[i] = sparse ? 0x24 : 255;
        uint64_t expected;
        unsigned flags = 0;
        if (trial == 4) {
            /* Only indices1 and33 active: opposite infinities cross v8/v9. */
            for (unsigned i = 0; i < 32; ++i) mask[i] = 0;
            mask[0] = mask[4] = 2;
            source[1] = 0x7f800000;
            source[33] = 0xff800000;
            expected = UINT64_C(0x7ff8000000000000);
            flags = 16;
        } else {
            for (unsigned i = 0; i < vl; ++i)
                if ((mask[i / 8] >> (i % 8)) & 1) sum += 1 + i % 7;
            expected = integer_bits(sum, 52, 1023);
        }
        /* Reuse the unmodified original m8 assembly helpers, including their
         * FP32 source group, FP64 singleton seed/destination and fcsr handling.
         */
        unsigned long status = (op ? m8widen_op_1 : m8widen_op_0)(
            source, seed, output + 1, vl, 256, mask, 0);
        __asm__ volatile("fence; csrr zero,vl" ::: "memory");
        if ((uint32_t)status) return replay_mismatch(5 * op + trial, ~0UL, 0, (uint32_t)status);
        if (status >> 32 != flags) return replay_mismatch(5 * op + trial, ~1UL, flags, status >> 32);
        if (output[1] != expected) return replay_mismatch(5 * op + trial, 1, expected, output[1]);
        for (unsigned i = 0; i < 18; ++i)
            if (i != 1 && output[i] != 0x5b) return replay_mismatch(5 * op + trial, i, 0x5b, output[i]);
    }
    replay_text("EXTENDED_PASS m8widen_nonzero cases=10\n");
    return 0;
}
#elif REPLAY_EXT == 4
extern unsigned long wholemove_layout_run(const void *, void *, void *, unsigned long, unsigned long);

int extension_main(void) {
    static uint8_t source[256] __attribute__((aligned(64)));
    static uint8_t destination[256] __attribute__((aligned(64)));
    static uint8_t dependent[256] __attribute__((aligned(64)));
    for (unsigned mode = 0; mode < 2; ++mode) for (unsigned noop = 0; noop < 2; ++noop) {
        for (unsigned i = 0; i < 256; ++i) {
            source[i] = (37 * i + 3) & 255;
            destination[i] = 91;
            dependent[i] = 99;
        }
        unsigned bytes = mode ? 2 : 1;
        unsigned start = noop ? 256 / bytes : 1;
        unsigned long status = wholemove_layout_run(source, destination, dependent, mode, start);
        if (status) return replay_mismatch(2 * mode + noop, ~0UL, 0, status);
        for (unsigned i = 0; i < 256; ++i) {
            uint8_t expected = i < start * bytes ? 91 : source[i];
            if (destination[i] != expected)
                return replay_mismatch(2 * mode + noop, i, expected, destination[i]);
            if (dependent[i] != expected)
                return replay_mismatch(2 * mode + noop, i + 256, expected, dependent[i]);
        }
    }
    replay_text("EXTENDED_PASS wholemove_layout cases=4\n");
    return 0;
}
#else
#error Unknown extension case
#endif
