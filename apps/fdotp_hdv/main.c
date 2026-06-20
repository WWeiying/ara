#include <stdint.h>
#include <stddef.h>
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

#define DOTP_AVL 1024

#ifndef FDOTP_HDV_TASK_ENTRY
#define FDOTP_HDV_TASK_ENTRY 0x80001000UL
#endif

extern double v64a[] __attribute__((aligned(32 * NR_LANES), section(".l2")));
extern double v64b[] __attribute__((aligned(32 * NR_LANES), section(".l2")));

// 64-bit dot product (e64, LMUL=8), HDV-packetised counterpart of fdotp_asm.
double fdotp_v64b(const double *a, const double *b, size_t avl);

int main() {
    fdotp_v64b(v64a, v64b, DOTP_AVL);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
double fdotp_v64b(const double *a, const double *b, size_t avl) {
    // ABI: a0=a, a1=b, a2=avl.  Result in fa0.  e64/LMUL=8 (VLMAX=128 @ VLEN=1024).
    //
    // HDV packetisation (accumulate-then-reduce; reduction is OUTSIDE the loop):
    //   setup = vsetvli || vmv.v.i v24,0 || vmv.v.i v0,0   (clear acc + seed)
    //   EP0   = vsetvli || vle(v8,a)                       (sub carried via cross)
    //   EP1   = sub || vle(v16,b) || slli || vfmacc(v24)
    //   EP2   = add a0 || add a1
    //   EP3   = bnez                                       (loop_end)
    //   tail  = vfredusum(v0,v24) ; vfmv.f.s fa0,v0 ; ret  (5.1 writeback)
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "fdotp_hdv_task_start:\n"

    // setup: configure e64/m8 VL, clear vector accumulator v24 and seed v0.
    "HDV_HINT 0x0a\n"
    "vsetvli t0, a2, e64, m8, ta, ma\n"
    "vmv.v.i v24, 0\n"
    "vmv.v.i v0, 0\n"

    // packet 0 (loop top): EP0 = vsetvli || vle(v8).  sub cut + cross=1.
    "dotp_loop:\n"
    "HDV_HINT 0x02, 0, 1, 1, 0\n"
    "vsetvli t0, a2, e64, m8, ta, ma\n"
    "vle64.v v8, (a0)\n"
    "sub a2, a2, t0\n"

    // packet 1: EP1 = carried sub || vle(v16) || slli || vfmacc.  slli writes the
    // e64 byte stride (vl*8); vfmacc accumulates a*b into v24 (Ara vector dep).
    "HDV_HINT\n"
    "vle64.v v16, (a1)\n"
    "slli t1, t0, 3\n"
    "vfmacc.vv v24, v8, v16\n"

    // packet 2: EP2 = add a0 || add a1 (both consume t1 from EP1).
    "HDV_HINT 0x02\n"
    "add a0, a0, t1\n"
    "add a1, a1, t1\n"
    "nop\n"

    // packet 3: EP3 = bnez (loop_end).
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a2, dotp_loop\n"
    "nop\n"
    "nop\n"

    // tail: reduce v24 into v0, move to fa0 (vector->scalar writeback), ret.
    "HDV_HINT 0x00\n"
    "vfredusum.vs v0, v24, v0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vfmv.f.s fa0, v0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
