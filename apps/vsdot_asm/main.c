// ============================================================================
// vsdot_asm — tightly-coupled (standard Ara) counterpart of vsdot_hdv.
// Auto-derived from the HDV version: HDV packetization stripped (HDV_HINT
// lui-x0 packet headers removed; .hdv_task section -> .text naked function).
// Identical vector instruction stream; the scalar core issues vector ops
// directly to Ara (no decoupled front-end / no software prefetch hints).
// For main-branch tightly-coupled architecture testing.  NOT yet tested.
// ============================================================================
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

// Uniform AVL knob: build with `make bin/vsdot_asm asm_avl=<n>` to sweep the
// 1D reduction length the kernel is CALLED with.  Defaults to TOTAL_ELEMENTS so
// a plain make is byte-identical to before.
#ifndef ASM_AVL
#define ASM_AVL TOTAL_ELEMENTS
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
    HW_CNT_READY;
#ifndef SPIKE
    perf_time();
#endif
    vsdot(src1, src2, ASM_AVL);
#ifndef SPIKE
    perf_time();
#endif
    HW_CNT_NOT_READY;
    return 0;
}

__attribute__((naked, 
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
    ".balign 16\n"
    "vsdot_hdv_task_start:\n"

    // setup: configure VL and clear the reduction accumulator v0.
    "vsetvli t0, a2, e32, m1, ta, ma\n"
    "vmv.v.i v0, 0\n"
    "nop\n"

    // packet 0 (loop top): EP0 = vsetvli || vle(v8).  sub is cut (pbits[3]=0)
    // and cross=1 carries it into packet 1.
    "dotp_loop:\n"
    "vsetvli t0, a2, e32, m1, ta, ma\n"
    "vle32.v v8, (a0)\n"
    "sub a2, a2, t0\n"

    // packet 1: EP1 = carried sub || vle(v16) || slli || vfmul.  slli writes the
    // byte stride t1; vfmul reads v8/v16 (vector deps handled by Ara).
    "vle32.v v16, (a1)\n"
    "slli t1, t0, 2\n"
    "vfmul.vv v24, v8, v16\n"

    // packet 2: EP2 = add a0 || vfredsum || add a1.  vfredsum accumulates into
    // v0 across iterations (Ara handles the reduction chain).
    "add a0, a0, t1\n"
    "vfredsum.vs v0, v24, v0\n"
    "add a1, a1, t1\n"

    // packet 3: EP3 = bnez (forces its own EP; loop_end marker).
    "bnez a2, dotp_loop\n"
    "nop\n"
    "nop\n"

    // tail: move the reduced scalar to fa0 (vector->scalar writeback), then ret
    // terminates the HDV task.  The nops are only packet padding.
    "vfmv.f.s fa0, v0\n"
    "nop\n"
    "nop\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
