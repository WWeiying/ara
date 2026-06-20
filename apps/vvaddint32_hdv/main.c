#include <stdint.h>
#include <string.h>

#include "runtime.h"
#include "util.h"

#ifdef SPIKE
#include <stdio.h>
#elif defined ARA_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

#define TOTAL_ELEMENTS 1024

// 16-byte aligned HDV task entry used by the mock host/TB.
// Override with: make -C apps bin/vvaddint32_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VVADDINT32_HDV_TASK_ENTRY
#define VVADDINT32_HDV_TASK_ENTRY 0x80001000UL
#endif

extern int32_t src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern int32_t src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));
extern int32_t dest[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.dest")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;
extern const uint32_t _dest_size;

// dst[i] = src1[i] + src2[i]
void vvaddint32(int n, const int *src1, const int *src2, int *dst);

int main() {
    vvaddint32(TOTAL_ELEMENTS, src1, src2, dest);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vvaddint32(int n, const int *src1, const int *src2, int *dst) {
    // ABI on entry: a0 = n, a1 = src1, a2 = src2, a3 = dst.
    //
    // HDV packetisation (5 EPs per loop iteration; LMUL=2):
    //   EP0 = vsetvli || vle(v0,src1)             (sub tail-carries via cross=1)
    //   EP1 = sub || slli || add a1 || vle(v8,src2)
    //   EP2 = add a2 || vadd || vse(dst)
    //   EP3 = add a3
    //   EP4 = bnez
    // On loop exit the fall-through ret is the final scalar EP and ends the task.
    //
    // Pointer-bump ordering relies on EP-level program order:
    //   - vle(v8) in EP1 reads a2 before add a2 (EP2) increments it.
    //   - vse(dst) in EP2 reads a3 before add a3 (EP3) increments it.
    // The byte stride t1 (= vl*4) is produced by slli and consumed by the three
    // pointer adds across EPs; cross-EP scalar reads are protected by EP order.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vvaddint32_hdv_task_start:\n"

    // packet 0: EP0 = vsetvli || vle32(v0,src1).  Cut before sub; cross=1 carries
    // sub into packet 1.
    "loop:\n"
    "HDV_HINT 0x02, 0, 1, 1, 0\n"
    "vsetvli t0, a0, e32, m2, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "sub a0, a0, t0\n"

    // packet 1: EP1 = carried sub || slli || add a1 || vle32(v8,src2).
    // slli writes the byte stride t1; add a1 (same EP, later slot) consumes it.
    // vle(v8) snapshots the current src2 base before EP2 bumps a2.
    "HDV_HINT 0x0a\n"
    "slli t1, t0, 2\n"
    "add a1, a1, t1\n"
    "vle32.v v8, (a2)\n"

    // packet 2: EP2 = add a2 || vadd || vse32(dst).  vadd consumes v0/v8 (Ara
    // handles the vector RAW); vse snapshots the current dst base before EP3
    // bumps a3.
    "HDV_HINT 0x0a\n"
    "add a2, a2, t1\n"
    "vadd.vv v16, v0, v8\n"
    "vse32.v v16, (a3)\n"

    // packet 3: EP3 = add a3, then bnez forces a cut (EP4).  ret is the
    // fall-through task terminator on loop exit.
    "HDV_HINT 0x1f, 0, 0, 0, 1\n"
    "add a3, a3, t1\n"
    "bnez a0, loop\n"
    "ret\n"

    // packet 4: padding after ret; not executed as business EPs.
    "HDV_HINT\n"
    "nop\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
