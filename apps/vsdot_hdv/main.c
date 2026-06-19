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
// Override with: make -C apps bin/vsdot_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VSDOT_HDV_TASK_ENTRY
#define VSDOT_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));
extern float dest[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.dest")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;
extern const uint32_t _dest_size;

// fa0 = sum(a[i] * b[i]), i = 0..avl-1
float vsdot(const float *a, const float *b, int avl);

int main() {
    vsdot(src1, src2, TOTAL_ELEMENTS);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv")))
float vsdot(const float *a, const float *b, int avl) {
    // ABI on entry: a0 = a, a1 = b, a2 = avl.  Result returned in fa0.
    //
    // HDV packetisation (single strip-mine loop + final reduction writeback):
    //   setup = vsetvli || vmv.v.i v0,0           (zero the reduction acc)
    //   EP0   = vsetvli || vle(v8,a)              (sub tail-carries via cross=1)
    //   EP1   = sub || vle(v16,b) || slli || vfmul
    //   EP2   = add a0 || vfredsum(v0) || add a1  (reduction chains in v0)
    //   EP3   = bnez                              (loop_end)
    //   tail  = vfmv.f.s fa0,v0 ; ret             (5.1 vector->scalar writeback)
    //
    // vsetvli rd=t0 is read by sub/slli in a LATER EP, so the vset VL writeback
    // lands before those scalars read t0 (A2-safe).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16))\n"
    ".endm\n"
    ".balign 16\n"
    "vsdot_hdv_task_start:\n"

    // setup: configure VL and clear the reduction accumulator v0.
    "HDV_HINT 0x02\n"
    "vsetvli t0, a2, e32, m1, ta, ma\n"
    "vmv.v.i v0, 0\n"
    "nop\n"

    // packet 0 (loop top): EP0 = vsetvli || vle(v8).  sub is cut (pbits[3]=0)
    // and cross=1 carries it into packet 1.
    "dotp_loop:\n"
    "HDV_HINT 0x02, 0, 1, 1, 0\n"
    "vsetvli t0, a2, e32, m1, ta, ma\n"
    "vle32.v v8, (a0)\n"
    "sub a2, a2, t0\n"

    // packet 1: EP1 = carried sub || vle(v16) || slli || vfmul.  slli writes the
    // byte stride t1; vfmul reads v8/v16 (vector deps handled by Ara).
    "HDV_HINT\n"
    "vle32.v v16, (a1)\n"
    "slli t1, t0, 2\n"
    "vfmul.vv v24, v8, v16\n"

    // packet 2: EP2 = add a0 || vfredsum || add a1.  vfredsum accumulates into
    // v0 across iterations (Ara handles the reduction chain).
    "HDV_HINT 0x0a\n"
    "add a0, a0, t1\n"
    "vfredsum.vs v0, v24, v0\n"
    "add a1, a1, t1\n"

    // packet 3: EP3 = bnez (forces its own EP; loop_end marker).
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a2, dotp_loop\n"
    "nop\n"
    "nop\n"

    // tail: move the reduced scalar to fa0 (vector->scalar writeback), then ret
    // terminates the HDV task.  The nops are only packet padding.
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
