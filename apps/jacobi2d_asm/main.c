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

extern const uint64_t R;
extern const uint64_t C;
extern double A_v[] __attribute__((aligned(8 * NR_LANES)));
extern double B_v[] __attribute__((aligned(8 * NR_LANES)));

// 5-point Jacobi 2D stencil (one timestep, one vector-width column strip):
//   B[i][j] = 0.2*(A[i][j-1] + A[i][j+1] + A[i-1][j] + A[i+1][j] + A[i][j])
// Left/right neighbours come from vfslide1up/down with the scalar boundary
// elements; top/middle/bottom rows are kept in vector registers and rotated.
// Clean (non-unrolled) hand-asm derived from the intrinsics j2d_kernel_v; the
// plain-Ara baseline of jacobi2d_hdv.
void j2d_kernel_v(uint64_t r, uint64_t c, double *A, double *B);

int main() {
    j2d_kernel_v(R, C, A_v, B_v);
    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void j2d_kernel_v(uint64_t r, uint64_t c, double *A, double *B) {
    // ABI: a0=r, a1=c, a2=A, a3=B.  Vectors (e64/m4): v0=top v4=mid v8=bottom
    // v12=left v16=right v20=tmp.  Running scalar pointers: a5=next-row-to-load,
    // a6=B[i], a7=&A[i][0] (izq), t4=&A[i][1+gvl] (der).
    __asm__ volatile (
        // fs0 = 0.2 = 1.0 / 5.0 (deterministic constant build).
        "li t0, 1\n"
        "fcvt.d.w ft2, t0\n"
        "li t0, 5\n"
        "fcvt.d.w ft3, t0\n"
        "fdiv.d fs0, ft2, ft3\n"
        // row stride bytes, row count, vector length for one column strip.
        "slli t6, a1, 3\n"           // t6 = c * 8 (row stride)
        "addi t5, a0, -2\n"          // t5 = size_y (interior rows)
        "addi t0, a1, -2\n"          // t0 = size_x
        "vsetvli a4, t0, e64, m4, ta, ma\n"   // a4 = gvl
        // initial three rows for column chunk j=1: top/mid/bottom.
        "addi t1, a2, 8\n"           // &A[0*c+1]
        "vle64.v v0, (t1)\n"
        "add t1, t1, t6\n"           // &A[1*c+1] (mid)
        "vle64.v v4, (t1)\n"
        "add t2, t1, t6\n"           // &A[2*c+1] (bottom)
        "vle64.v v8, (t2)\n"
        "add a5, t2, t6\n"           // p_next = &A[3*c+1]
        // output + scalar boundary pointers (row i=1).
        "addi a6, a3, 8\n"
        "add a6, a6, t6\n"           // pB = &B[1*c+1]
        "add a7, a2, t6\n"           // p_izq = &A[1*c+0]
        "slli t3, a4, 3\n"           // gvl * 8
        "add t4, t1, t3\n"           // p_der = &A[1*c+1+gvl]
        "j2d_row_loop:\n"
        "fld ft0, 0(a7)\n"           // izq = A[i][0]
        "fld ft1, 0(t4)\n"           // der = A[i][1+gvl]
        "vfslide1up.vf v12, v4, ft0\n"   // left  neighbours
        "vfslide1down.vf v16, v4, ft1\n" // right neighbours
        "vfadd.vv v20, v12, v16\n"
        "vfadd.vv v20, v20, v0\n"        // + top
        "vfadd.vv v20, v20, v8\n"        // + bottom
        "vfadd.vv v20, v20, v4\n"        // + middle
        "vfmul.vf v20, v20, fs0\n"       // * 0.2
        "vse64.v v20, (a6)\n"            // store B[i]
        "vmv.v.v v0, v4\n"               // rotate: top = mid
        "vmv.v.v v4, v8\n"               // mid = bottom
        "vle64.v v8, (a5)\n"             // bottom = next row
        "add a5, a5, t6\n"
        "add a6, a6, t6\n"
        "add a7, a7, t6\n"
        "add t4, t4, t6\n"
        "addi t5, t5, -1\n"
        "bnez t5, j2d_row_loop\n"
        "ret\n"
    );
}
