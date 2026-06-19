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

extern const uint64_t M;
extern const uint64_t N;
extern const uint64_t P;
extern double a[] __attribute__((aligned(32 * NR_LANES), section(".l2")));
extern double b[] __attribute__((aligned(32 * NR_LANES), section(".l2")));
extern double c[] __attribute__((aligned(32 * NR_LANES), section(".l2")));

// C = A * B (fp64).  Clean 4-row-blocked matmul over ONE e64/m4 column block
// (the first VLMAX columns), derived from fmatmul_4x4 and simplified (single
// column block, no b double-buffering).  Plain-Ara baseline of fmatmul_hdv.
void fmatmul_clean(double *c, const double *a, const double *b,
                   uint64_t M, uint64_t N, uint64_t P);

int main() {
    fmatmul_clean(c, a, b, M, N, P);
    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void fmatmul_clean(double *c, const double *a, const double *b,
                   uint64_t M, uint64_t N, uint64_t P) {
    // ABI: a0=c, a1=a, a2=b, a3=M, a4=N, a5=P.
    // e64/m4: v0,v4,v8,v12 = 4 row accumulators; v16 = B[k][:] row.
    __asm__ volatile (
        "vsetvli t0, a5, e64, m4, ta, ma\n"   // gvl columns (one block)
        "slli s0, a4, 3\n"                    // A row stride = N*8
        "slli s1, a5, 3\n"                    // B/C row stride = P*8
        "srli s2, a3, 2\n"                    // row-block count = M/4
        "mv t1, a1\n"                         // A row-block base
        "mv t2, a0\n"                         // C row-block base
        "fm_rowblk:\n"
        "vmv.v.i v0, 0\n"
        "vmv.v.i v4, 0\n"
        "vmv.v.i v8, 0\n"
        "vmv.v.i v12, 0\n"
        "mv t3, t1\n"                         // &A[m+0][0]
        "add t4, t1, s0\n"                    // &A[m+1][0]
        "add t5, t4, s0\n"                    // &A[m+2][0]
        "add t6, t5, s0\n"                    // &A[m+3][0]
        "mv a6, a2\n"                         // &B[0][0]
        "mv a7, a4\n"                         // k counter = N
        "fm_kloop:\n"
        "fld ft0, 0(t3)\n"
        "fld ft1, 0(t4)\n"
        "fld ft2, 0(t5)\n"
        "fld ft3, 0(t6)\n"
        "vle64.v v16, (a6)\n"                 // B[k][:]
        "vfmacc.vf v0, ft0, v16\n"
        "vfmacc.vf v4, ft1, v16\n"
        "vfmacc.vf v8, ft2, v16\n"
        "vfmacc.vf v12, ft3, v16\n"
        "addi t3, t3, 8\n"
        "addi t4, t4, 8\n"
        "addi t5, t5, 8\n"
        "addi t6, t6, 8\n"
        "add a6, a6, s1\n"                    // next B row
        "addi a7, a7, -1\n"
        "bnez a7, fm_kloop\n"
        "vse64.v v0, (t2)\n"                  // store C[m+0]
        "add s3, t2, s1\n"
        "vse64.v v4, (s3)\n"                  // C[m+1]
        "add s3, s3, s1\n"
        "vse64.v v8, (s3)\n"                  // C[m+2]
        "add s3, s3, s1\n"
        "vse64.v v12, (s3)\n"                 // C[m+3]
        "slli s4, s0, 2\n"
        "add t1, t1, s4\n"                    // A += 4 rows
        "slli s4, s1, 2\n"
        "add t2, t2, s4\n"                    // C += 4 rows
        "addi s2, s2, -1\n"
        "bnez s2, fm_rowblk\n"
        "ret\n"
    );
}
