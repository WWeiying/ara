// ============================================================================
// vmc_asm — tightly-coupled (standard Ara) counterpart of vmc_hdv.
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

#ifndef VMC_HDV_TASK_ENTRY
#define VMC_HDV_TASK_ENTRY 0x80001000UL
#endif

#ifndef ASM_AVL
#define ASM_AVL TOTAL_ELEMENTS
#endif

extern int32_t src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern int32_t src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));
extern int32_t dest[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.dest")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;
extern const uint32_t _dest_size;

// dst[i] = (src[i] * scalar) >> 3, widening e16->e32 (the vmc "vec_mul_shift"
// kernel, ported from the commented-out asm in the original vmc/main.c).
void vec_mul_shift(int n, const short *src, int *dst, int scalar);

int main() {
    HW_CNT_READY;
#ifndef SPIKE
    perf_time();
#endif
    vec_mul_shift(ASM_AVL, (const short *)src1, dest, 3);
#ifndef SPIKE
    perf_time();
#endif
    HW_CNT_NOT_READY;
    return 0;
}

__attribute__((naked, 
               target("arch=rv64gcv")))
void vec_mul_shift(int n, const short *src, int *dst, int scalar) {
    // ABI: a0=n, a1=src, a2=dst, a3=scalar.
    //
    // Single strip-mine loop with a widening multiply.  t0 saves the scalar
    // multiplier BEFORE vsetvli clobbers a3 (vsetvli rd=a3 = granted e16 VL).
    // The second vsetvli reinterprets the widened result as e32/m8.  vsetvli
    // rd=a3 is read by slli only in later EPs (A2-safe); vwmul.vx reads t0 (a
    // stable scalar set in setup).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vmc_hdv_task_start:\n"

    // setup: save the scalar multiplier, guard against n==0.
    "mv t0, a3\n"
    "nop\n"
    "nop\n"
    "beqz a0, exit_loop\n"
    "nop\n"
    "nop\n"

    // loop top: e16/m4 config || load e16 chunk.
    "loop_start:\n"
    "vsetvli a3, a0, e16, m4, ta, ma\n"
    "vle16.v v4, (a1)\n"
    "nop\n"
    // e16 byte stride (a3 = granted VL) then bump src.
    "slli t1, a3, 1\n"
    "nop\n"
    "nop\n"
    "add a1, a1, t1\n"
    "nop\n"
    "nop\n"
    // widening multiply: v8(e32) = v4(e16) * scalar.
    "vwmul.vx v8, v4, t0\n"
    "nop\n"
    "nop\n"
    // reinterpret as e32/m8, shift right by 3, store.
    "vsetvli zero, zero, e32, m8, ta, ma\n"
    "nop\n"
    "nop\n"
    "vsrl.vi v8, v8, 3\n"
    "nop\n"
    "nop\n"
    "vse32.v v8, (a2)\n"
    "nop\n"
    "nop\n"
    // e32 byte stride then bump dst || decrement remaining.
    "slli t1, a3, 2\n"
    "nop\n"
    "nop\n"
    "add a2, a2, t1\n"
    "sub a0, a0, a3\n"
    "nop\n"
    // back-edge.
    "bnez a0, loop_start\n"
    "nop\n"
    "nop\n"

    // exit: ret terminates the HDV task.
    "exit_loop:\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
