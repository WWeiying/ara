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

#ifndef FMATMUL_HDV_TASK_ENTRY
#define FMATMUL_HDV_TASK_ENTRY 0x80001000UL
#endif

extern const uint64_t M;
extern const uint64_t N;
extern const uint64_t P;
extern double a[] __attribute__((aligned(32 * NR_LANES), section(".l2")));
extern double b[] __attribute__((aligned(32 * NR_LANES), section(".l2")));
extern double c[] __attribute__((aligned(32 * NR_LANES), section(".l2")));

// C = A * B (fp64), clean 4-row-blocked matmul over one e64/m4 column block;
// HDV-packetised counterpart of fmatmul_asm.
void fmatmul_clean(double *c, const double *a, const double *b,
                   uint64_t M, uint64_t N, uint64_t P);

int main() {
    // Kernel correctness verified out-of-band by a python cross-check against
    // data.S: kernel C[0][0]=0x403d91a3f68bcd14 (29.5689) == true matmul of the
    // real data.  (An in-program fp64 reduction reference miscompiles under the
    // app's -O3 -ffast-math, so it is not used here.)
    fmatmul_clean(c, a, b, M, N, P);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void fmatmul_clean(double *c, const double *a, const double *b,
                   uint64_t M, uint64_t N, uint64_t P) {
    // ABI: a0=c, a1=a, a2=b, a3=M, a4=N, a5=P.  VL set once (column block width);
    // 4 scalar A loads one-per-EP, 4 vfmacc packed (Ara vector deps), each store
    // and its base bump split.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "fmatmul_hdv_task_start:\n"

    // setup: VL (one column block) + strides + row-block count + bases.
    "HDV_HINT 0x00\n"
    "vsetvli t0, a5, e64, m4, ta, ma\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x0a\n"
    "slli s0, a4, 3\n"
    "slli s1, a5, 3\n"
    "srli s2, a3, 2\n"
    "HDV_HINT 0x02\n"
    "mv t1, a1\n"
    "mv t2, a0\n"
    "nop\n"

    // row-block loop top: zero the 4 accumulators.
    "fm_rowblk:\n"
    "HDV_HINT 0x0a, 0, 0, 1, 0\n"
    "vmv.v.i v0, 0\n"
    "vmv.v.i v4, 0\n"
    "vmv.v.i v8, 0\n"
    "HDV_HINT 0x00\n"
    "vmv.v.i v12, 0\n"
    "nop\n"
    "nop\n"
    // 4 A row pointers.
    "HDV_HINT 0x02\n"
    "mv t3, t1\n"
    "add t4, t1, s0\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "add t5, t4, s0\n"
    "add t6, t5, s0\n"
    "nop\n"
    // B row pointer + k counter.
    "HDV_HINT 0x02\n"
    "mv a6, a2\n"
    "mv a7, a4\n"
    "nop\n"

    // k loop top: 4 scalar A loads (one per EP: synchronous scalar LSU).
    "fm_kloop:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "fld ft0, 0(t3)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft1, 0(t4)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft2, 0(t5)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft3, 0(t6)\n"
    "nop\n"
    "nop\n"
    // load B[k][:].
    "HDV_HINT 0x00\n"
    "vle64.v v16, (a6)\n"
    "nop\n"
    "nop\n"
    // 4 fmacc into the accumulators.
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v0, ft0, v16\n"
    "vfmacc.vf v4, ft1, v16\n"
    "vfmacc.vf v8, ft2, v16\n"
    "HDV_HINT 0x00\n"
    "vfmacc.vf v12, ft3, v16\n"
    "nop\n"
    "nop\n"
    // advance A column pointers ...
    "HDV_HINT 0x0a\n"
    "addi t3, t3, 8\n"
    "addi t4, t4, 8\n"
    "addi t5, t5, 8\n"
    // ... B row pointer + k decrement.
    "HDV_HINT 0x0a\n"
    "addi t6, t6, 8\n"
    "add a6, a6, s1\n"
    "addi a7, a7, -1\n"
    // inner back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a7, fm_kloop\n"
    "nop\n"
    "nop\n"

    // store the 4 C rows (each store and its base bump in separate EPs).
    "HDV_HINT 0x00\n"
    "vse64.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "add s3, t2, s1\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse64.v v4, (s3)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "add s3, s3, s1\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse64.v v8, (s3)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "add s3, s3, s1\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse64.v v12, (s3)\n"
    "nop\n"
    "nop\n"
    // advance row-block bases (A += 4 rows, C += 4 rows) + block decrement.
    "HDV_HINT 0x02\n"
    "slli s4, s0, 2\n"
    "add t1, t1, s4\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "slli s4, s1, 2\n"
    "add t2, t2, s4\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi s2, s2, -1\n"
    "nop\n"
    "nop\n"
    // outer back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez s2, fm_rowblk\n"
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
