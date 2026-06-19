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

#define TOTAL_ELEMENTS 64*64 
#define TEST_ELEMENTS  512

#define M 24 
#define N 
#define K 2
#define A_NUM M*K
#define B_NUM K*N
#define C_NUM M*N

extern float src1[4096] __attribute__((aligned(4), section(".data.src1")));
extern float src2[4096] __attribute__((aligned(4), section(".data.src2")));
extern float dest[4096] __attribute__((aligned(4), section(".data.dest")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;
extern const uint32_t _dest_size;

// Function prototype using vector extension
void vgemm(size_t n, size_t m, size_t k, const float* a, size_t lda, const float* b, size_t ldb, float* c, size_t ldc);

int main() {
int m,n,k;
    m=32;
    n=32;
    k=16;
    vgemm(n, m, k, src1, k, src2, n, dest, n);
#ifndef SPIKE
    perf_time();
#endif
    return 0;
}


#ifdef vec
__attribute__((noinline, used)) void vsaxpy(int n, const float a, const float *src1, float *src2) {
    for (int i=0; i<n; i++) {
        src2[i]=a*src1[i]+src2[i];
    }
}
#else
__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void vgemm(size_t n, size_t m, size_t k, const float* a, size_t lda, const float* b, size_t ldb, float* c, size_t ldc) {
    __asm__ volatile (
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        "addi sp, sp, -32\n"
        "sd s0, 0(sp)\n"
        "sd s1, 8(sp)\n"
        "sd s2, 16(sp)\n"
        "sd s3, 24(sp)\n"
        "beqz a0, exit\n"
        "beqz a1, exit\n"
        "beqz a2, exit\n"
        "ld t0, 32(sp)\n"
        "slli a4, a4, 2\n"
        "slli a6, a6, 2\n"
        "slli t0, t0, 2\n"
        "slti t6, a1, 16\n"
        "bnez t6, end_rows\n"

        "c_row_loop:\n"
        "mv t2, a0\n"
        "mv t3, a5\n"
        "mv t4, a7\n"

        "c_col_loop:\n"
        "vsetvli s1, t2, e32, ta, ma\n"
        "mv t5, a3\n"
        "mv s0, t3\n"
        "vle32.v v0, (t4)\n"
        "add s2, t4, t0\n"
        "vle32.v v1, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v2, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v3, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v4, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v5, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v6, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v7, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v8, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v9, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v10, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v11, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v12, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v13, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v14, (s2)\n"
        "add s2, s2, t0\n"
        "vle32.v v15, (s2)\n"
        "mv t1, a2\n"
        "flw fa0, (t5)\n"
        "add s3, t5, a4\n"
        "flw fa1, (s3)\n"
        "add s3, s3, a4\n"
        "flw fa2, (s3)\n"
        "add s3, s3, a4\n"
        "flw fa3, (s3)\n"
        "add s3, s3, a4\n"
        "vle32.v v16, (s0)\n"

        "k_loop:\n"
        "vfmacc.vf v0, fa0, v16\n"
        "add s0, s0, a6\n"
        "flw fa4, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v1, fa1, v16\n"
        "addi t1, t1, -1\n"
        "flw fa5, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v2, fa2, v16\n"
        "flw fa6, (s3)\n"
        "add s3, s3, a4\n"
        "flw fa7, (s3)\n"
        "vfmacc.vf v3, fa3, v16\n"
        "add s3, s3, a4\n"
        "flw ft0, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v4, fa4, v16\n"
        "flw ft1, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v5, fa5, v16\n"
        "flw ft2, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v6, fa6, v16\n"
        "flw ft3, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v7, fa7, v16\n"
        "flw ft4, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v8, ft0, v16\n"
        "flw ft5, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v9, ft1, v16\n"
        "flw ft6, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v10, ft2, v16\n"
        "flw ft7, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v11, ft3, v16\n"
        "beqz t1, 1f\n"
        "flw fa0, (t5)\n"
        "add s3, t5, a4\n"
        "1: vfmacc.vf v12, ft4, v16\n"
        "beqz t1, 1f\n"
        "flw fa1, (s3)\n"
        "add s3, s3, a4\n"
        "1: vfmacc.vf v13, ft5, v16\n"
        "beqz t1, 1f\n"
        "flw fa2, (s3)\n"
        "add s3, s3, a4\n"
        "1: vfmacc.vf v14, ft6, v16\n"
        "beqz t1, 1f\n"
        "flw fa3, (s3)\n"
        "add s3, s3, a4\n"
        "vfmacc.vf v15, ft7, v16\n"
        "vle32.v v16, (s0)\n"
        "j k_loop\n"
        "1: vfmacc.vf v15, ft7, v16\n"
        "vse32.v v0, (t4)\n"
        "add s2, t4, t0\n"
        "vse32.v v1, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v2, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v3, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v4, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v5, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v6, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v7, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v8, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v9, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v10, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v11, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v12, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v13, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v14, (s2)\n"
        "add s2, s2, t0\n"
        "vse32.v v15, (s2)\n"
        "slli t6, s1, 2\n"
        "add t4, t4, t6\n"
        "add t3, t3, t6\n"
        "sub t2, t2, s1\n"
        "bnez t2, c_col_loop\n"
        "addi a1, a1, -16\n"
        "slli t6, a4, 4\n"
        "add a3, a3, t6\n"
        "slli t6, t0, 4\n"
        "add a7, a7, t6\n"
        "slti t6, a1, 16\n"
        "beqz t6, c_row_loop\n"
        "end_rows:\n"
        "exit:\n"
        "ld s0, 0(sp)\n"
        "ld s1, 8(sp)\n"
        "ld s2, 16(sp)\n"
        "ld s3, 24(sp)\n"
        "addi sp, sp, 32\n"
        "ret\n"
    );
}
#endif

//#ifdef vec
//__attribute__((noinline, used)) void vsaxpy(int n, const float a, const float *src1, float *src2) {
//    for (int i=0; i<n; i++) {
//        src2[i]=a*src1[i]+src2[i];
//    }
//}
//#else
//__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
//void vsaxpy(int n, const float a, const float *src1, float *src2) {
//    __asm__ volatile (
//    "rdcycle zero\n"
//    "saxpy:\n"
//    "vsetvli t0, a0, e32, m1, ta, ma\n"
//    "vle32.v v0, (a2)\n"
//    "sub a0, a0, t0\n"
//    "slli t1, t0, 2\n"
//    "add a2, a2, t1\n"
//    "vle32.v v8, (a3)\n"
//    "vfmacc.vf v8, fa0, v0\n"
//    "vse32.v v8, (a3)\n"
//    "add a3, a3, t1\n"
//    "bnez a0, saxpy\n"
//    "ret\n"
//    );
//}
//#endif
