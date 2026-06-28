// ============================================================================
// vsscal_asm — tightly-coupled (standard Ara) counterpart of vsscal_hdv.
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
#define TEST_ELEMENTS  512

// 16-byte aligned HDV task entry used by the mock host/TB.
// Override with: make -C apps bin/vsscal_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VSSCAL_HDV_TASK_ENTRY
#define VSSCAL_HDV_TASK_ENTRY 0x80001000UL
#endif

// Uniform AVL knob: `make bin/vsscal_asm asm_avl=<n>` injects -DASM_AVL=<n>.
// Defaults to TOTAL_ELEMENTS so a plain build is byte-identical to before.
#ifndef ASM_AVL
#define ASM_AVL TOTAL_ELEMENTS
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// dst[i] = a * src[i]
void vsscal(int n, const float a, const float *src, float *dst);

int main() {
    const float a = 6.66;

    HW_CNT_READY;
    #ifndef SPIKE
    perf_time();
    #endif
    vsscal(ASM_AVL, a, src1, src2);
    #ifndef SPIKE
    perf_time();
    #endif
    HW_CNT_NOT_READY;

    return 0;
}

__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void vsscal(int n, const float a, const float *src, float *dst) {
    // ABI on entry: a0 = n, fa0 = a, a1 = src, a2 = dst.
    //
    // HDV packetisation (mirrors vsaxpy_hdv; 4 EPs per loop iteration):
    //   EP0 = vsetvli || vle(v0,src)              (sub tail-carries via cross=1)
    //   EP1 = sub || slli || vfmul || add a1      (src pointer bump)
    //   EP2 = vse(dst) || add a2                  (store snapshots old a2)
    //   EP3 = bnez                                (branch forces its own EP)
    // On loop exit the fall-through ret is the final scalar EP and ends the task.
    //
    // vsetvli's rd=t0 is read by sub/slli: EP0 finishes its vset writeback before
    // EP1 issues, so the dependent scalars observe the granted VL (A2-safe).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsscal_hdv_task_start:\n"

    // packet 0: EP0 = vsetvli || vle32(v0).  Cut before sub (pbits[3]=0); cross=1
    // carries sub into packet 1.
    "loop:\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "sub a0, a0, t0\n"

    // packet 1: EP1 = carried sub || slli || vfmul || add a1.  slli writes the
    // byte stride t1 that add a1 consumes in the same EP (scalar slots execute
    // in slot order, so this RAW resolves correctly).  vfmul reads v0 produced
    // by EP0's load (Ara handles the vector dependency).
    "slli t1, t0, 2\n"
    "vfmul.vf v0, v0, fa0\n"
    "add a1, a1, t1\n"

    // packet 2: EP2 = vse32(old a2) || add a2.  The store snapshots a2 before the
    // pointer increment in the same EP, which is intended.  bnez forces a pack
    // cut, so it becomes EP3 on its own.
    "vse32.v v0, (a2)\n"
    "add a2, a2, t1\n"
    "bnez a0, loop\n"

    // packet 3: ret terminates the HDV task; the nops are only packet padding.
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
