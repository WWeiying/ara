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

#ifndef JACOBI2D_HDV_TASK_ENTRY
#define JACOBI2D_HDV_TASK_ENTRY 0x80001000UL
#endif

extern const uint64_t R;
extern const uint64_t C;
extern double A_v[] __attribute__((aligned(8 * NR_LANES)));
extern double B_v[] __attribute__((aligned(8 * NR_LANES)));

// 5-point Jacobi 2D stencil (one timestep, one vector-width column strip),
// HDV-packetised counterpart of jacobi2d_asm.
void j2d_kernel_v(uint64_t r, uint64_t c, double *A, double *B);

int main() {
    j2d_kernel_v(R, C, A_v, B_v);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void j2d_kernel_v(uint64_t r, uint64_t c, double *A, double *B) {
    // ABI: a0=r, a1=c, a2=A, a3=B.  e64/m4: v0=top v4=mid v8=bottom v12=left
    // v16=right v20=tmp.  Setup is one-shot; the row loop is packed conservatively
    // (scalar load-use, scalar->vector operand, vset-rd reads and the register
    // rotation are all split across EPs).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "j2d_hdv_task_start:\n"

    // fs0 = 0.2 = 1.0/5.0.
    "HDV_HINT 0x00\n"
    "li t0, 1\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fcvt.d.w ft2, t0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "li t0, 5\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fcvt.d.w ft3, t0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fdiv.d fs0, ft2, ft3\n"
    "nop\n"
    "nop\n"
    // strides/counters + VL config.
    "HDV_HINT 0x0a\n"
    "slli t6, a1, 3\n"
    "addi t5, a0, -2\n"
    "addi t0, a1, -2\n"
    "HDV_HINT 0x00\n"
    "vsetvli a4, t0, e64, m4, ta, ma\n"
    "nop\n"
    "nop\n"
    // initial three rows: top.
    "HDV_HINT 0x00\n"
    "addi t1, a2, 8\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle64.v v0, (t1)\n"
    "nop\n"
    "nop\n"
    // middle.
    "HDV_HINT 0x00\n"
    "add t1, t1, t6\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle64.v v4, (t1)\n"
    "nop\n"
    "nop\n"
    // bottom.
    "HDV_HINT 0x00\n"
    "add t2, t1, t6\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle64.v v8, (t2)\n"
    "nop\n"
    "nop\n"
    // running pointers: next-row, B[i], izq, der.
    "HDV_HINT 0x0a\n"
    "add a5, t2, t6\n"
    "addi a6, a3, 8\n"
    "slli t3, a4, 3\n"
    "HDV_HINT 0x0a\n"
    "add a6, a6, t6\n"
    "add a7, a2, t6\n"
    "add t4, t1, t3\n"

    // row loop top: load the two scalar boundary elements (one per EP).
    "j2d_row_loop:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "fld ft0, 0(a7)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft1, 0(t4)\n"
    "nop\n"
    "nop\n"
    // left/right neighbours via slides (read the freshly loaded scalars).
    "HDV_HINT 0x02\n"
    "vfslide1up.vf v12, v4, ft0\n"
    "vfslide1down.vf v16, v4, ft1\n"
    "nop\n"
    // accumulate the 5 contributions (vector chain).
    "HDV_HINT 0x0a\n"
    "vfadd.vv v20, v12, v16\n"
    "vfadd.vv v20, v20, v0\n"
    "vfadd.vv v20, v20, v8\n"
    "HDV_HINT 0x02\n"
    "vfadd.vv v20, v20, v4\n"
    "vfmul.vf v20, v20, fs0\n"
    "nop\n"
    // store B[i].
    "HDV_HINT 0x00\n"
    "vse64.v v20, (a6)\n"
    "nop\n"
    "nop\n"
    // rotate registers (top=mid, mid=bottom) before loading the new bottom.
    "HDV_HINT 0x02\n"
    "vmv.v.v v0, v4\n"
    "vmv.v.v v4, v8\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle64.v v8, (a5)\n"
    "nop\n"
    "nop\n"
    // advance running pointers + row counter.
    "HDV_HINT 0x0a\n"
    "add a5, a5, t6\n"
    "add a6, a6, t6\n"
    "add a7, a7, t6\n"
    "HDV_HINT 0x02\n"
    "add t4, t4, t6\n"
    "addi t5, t5, -1\n"
    "nop\n"
    // back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t5, j2d_row_loop\n"
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
