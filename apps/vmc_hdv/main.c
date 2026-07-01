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
    vec_mul_shift(TOTAL_ELEMENTS, (const short *)src1, dest, 3);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
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
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vmc_hdv_task_start:\n"

    // setup: save the scalar multiplier, guard against n==0.
    "HDV_HINT 0x00\n"
    "mv t0, a3\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "beqz a0, exit_loop\n"
    "nop\n"
    "nop\n"

    // loop top: e16/m4 config || load e16 chunk.
    "loop_start:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vsetvli a3, a0, e16, m4, ta, ma\n"
    "vle16.v v4, (a1)\n"
    "nop\n"
    // e16 byte stride (a3 = granted VL) then bump src.
    "HDV_HINT 0x00\n"
    "slli t1, a3, 1\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "add a1, a1, t1\n"
    "nop\n"
    "nop\n"
    // widening multiply: v8(e32) = v4(e16) * scalar.
    "HDV_HINT 0x00\n"
    "vwmul.vx v8, v4, t0\n"
    "nop\n"
    "nop\n"
    // reinterpret as e32/m8, shift right by 3, store.
    "HDV_HINT 0x00\n"
    "vsetvli zero, zero, e32, m8, ta, ma\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vsrl.vi v8, v8, 3\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v8, (a2)\n"
    "nop\n"
    "nop\n"
    // e32 byte stride then bump dst || decrement remaining.
    "HDV_HINT 0x00\n"
    "slli t1, a3, 2\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "add a2, a2, t1\n"
    "sub a0, a0, a3\n"
    "nop\n"
    // back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a0, loop_start\n"
    "nop\n"
    "nop\n"

    // exit: ret terminates the HDV task.
    "exit_loop:\n"
    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
