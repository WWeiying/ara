// SPDX-License-Identifier: SHL-0.51
// Prepared only: not compiled or simulated. Not part of the six-case repair gate.
#include <stdint.h>

#if !defined(NR_LANES) || NR_LANES != 4
#error "The stage-discriminating layout requires NR_LANES=4"
#endif
#if !defined(VLEN) || VLEN != 1024
#error "This diagnostic is prepared for the reviewed VLEN=1024 image"
#endif

// -1 runs the three candidates; 0/1/2 selects a single candidate.
#ifndef RED_MERGE_CASE
#define RED_MERGE_CASE (-1)
#endif
#if RED_MERGE_CASE < -1 || RED_MERGE_CASE > 2
#error "RED_MERGE_CASE must be -1, 0, 1, or 2"
#endif

static const uint32_t inputs[3][8] __attribute__((aligned(128))) = {
    {0x3f800000u, 0x34000000u, 0, 0, 0, 0, 0, 0},
    {0x3f800000u, 0x33800000u, 0, 0, 0, 0, 0, 0},
    {0x3f800000u, 0, 0, 0, 0x33800000u, 0, 0, 0},
};
static const unsigned lengths[3] = {2, 2, 5};
static const uint32_t expected_bits[3] = {
    0x3f800001u, 0x3f800000u, 0x3f800000u,
};
static const unsigned expected_flags[3] = {0, 1, 1};

// Nonzero failure bits: 0=VL, 1=result, 2=fflags, 3=vstart.
struct merge_observation {
    uint64_t vl;
    uint64_t result_bits;
    uint64_t fflags;
    uint64_t vstart;
    uint64_t failure_bits;
};
volatile struct merge_observation merge_observed[3];
volatile unsigned merge_started_mask, merge_completed_mask;
volatile unsigned g75_result[2];

int main(void) {
    for (unsigned i = 0; i < 3; ++i) {
        if (RED_MERGE_CASE >= 0 && i != (unsigned)RED_MERGE_CASE)
            continue;

        uint64_t vl, bits, flags, restart;
        merge_started_mask |= 1u << i;
        // Initialize both halves of each physical lane word. Only the later
        // VL=2/5 operation contributes source elements to the reduction.
        __asm__ volatile(
            "csrw vstart, zero\n"
            "vsetivli zero, 8, e32, m1, tu, mu\n"
            "vmv.v.i v1, 0\n"
            "vmv.v.i v2, 0\n"
            "vle32.v v8, (%[input])\n"
            "vsetvli %[vl], %[avl], e32, m1, tu, mu\n"
            "csrw fcsr, zero\n"
            "vfredusum.vs v2, v8, v1\n"
            "vmv.x.s %[bits], v2\n"
            "csrr %[flags], fflags\n"
            "csrr %[restart], vstart\n"
            : [vl] "=&r"(vl), [bits] "=&r"(bits),
              [flags] "=&r"(flags), [restart] "=&r"(restart)
            : [input] "r"(inputs[i]), [avl] "r"((uint64_t)lengths[i])
            : "memory", "v1", "v2", "v8");

        unsigned bad_vl = vl != lengths[i];
        unsigned bad_result = (uint32_t)bits != expected_bits[i];
        unsigned bad_flags = flags != expected_flags[i];
        unsigned bad_restart = restart != 0;
        merge_observed[i].vl = vl;
        merge_observed[i].result_bits = (uint32_t)bits;
        merge_observed[i].fflags = flags;
        merge_observed[i].vstart = restart;
        merge_observed[i].failure_bits = bad_vl | (bad_result << 1) |
                                        (bad_flags << 2) | (bad_restart << 3);
        g75_result[0] += 4;
        g75_result[1] += bad_vl + bad_result + bad_flags + bad_restart;
        merge_completed_mask |= 1u << i;
    }
    return g75_result[1] != 0;
}
