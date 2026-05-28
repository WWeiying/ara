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

#define TOTAL_ELEMENTS 16384
#define TEST_ELEMENTS  512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Function prototype using vector extension
void gemm_f32_32x32x32_4row(const float *A, const float *B, float *C);
void gemm_f32_64x64x64_4row(const float *A, const float *B, float *C);
void gemm_f32_128x128x128_4row(const float *A, const float *B, float *C);

int main() {
    const float a = 6.66;

    //gemm_f32_32x32x32_4row(src1,src2,src1);
    //gemm_f32_64x64x64_4row(src1,src2,src1);
    gemm_f32_128x128x128_4row(src1,src2,src1);

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_32x32x32_4row(const float *A, const float *B, float *C) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      // A: a0, B: a1, C: a2
      // row-major, FP32
      // M = N = K = 32
      // 4-row blocking:
      //   row i   accumulator: v8
      //   row i+1 accumulator: v9
      //   row i+2 accumulator: v10
      //   row i+3 accumulator: v11

      // FP32 on VLEN=1024 -> VLMAX = 32
      "li a3, 32\n"
      "vsetvli zero, a3, e32, m1, ta, ma\n"

      // row-block count = 32 / 4 = 8
      "li t0, 8\n"
      "mv t1, a0\n"                  // t1 = A row-block base (row i)
      "mv t2, a2\n"                  // t2 = C row-block base (row i)

      "row_block_loop_32:\n"
      // zero accumulators for 4 rows x 1 column chunk
      "vmv.v.i v8,  0\n"
      "vmv.v.i v9,  0\n"
      "vmv.v.i v10, 0\n"
      "vmv.v.i v11, 0\n"

      // A row pointers for rows i, i+1, i+2, i+3
      "mv t3, t1\n"                  // t3 = A[i][0]
      "addi t4, t1, 128\n"           // t4 = A[i+1][0], 32*4 = 128B
      "addi t5, t1, 256\n"           // t5 = A[i+2][0]
      "addi t6, t1, 384\n"           // t6 = A[i+3][0]

      // B row pointer and K counter
      "mv a3, a1\n"                  // a3 = B[0][0]
      "li a4, 1024\n"                  // a4 = k counter

      "k_loop_32:\n"
      "vsetvli zero, a4, e32, m1, ta, ma\n"
      // load 4 scalars: A[i+r][k], r = 0..3
      "flw fa0, 0(t3)\n"
      "flw fa1, 0(t4)\n"
      "flw fa2, 0(t5)\n"
      "flw fa3, 0(t6)\n"

      // load one full row of B[k][:]
      "vle32.v v0, (a3)\n"

      // Row i
      "vfmacc.vf v8,  fa0, v0\n"

      // Row i+1
      "vfmacc.vf v9,  fa1, v0\n"

      // Row i+2
      "vfmacc.vf v10, fa2, v0\n"

      // Row i+3
      "vfmacc.vf v11, fa3, v0\n"

      // Advance A row pointers and B row pointer
      "addi t3, t3, 4\n"
      "addi t4, t4, 4\n"
      "addi t5, t5, 4\n"
      "addi t6, t6, 4\n"
      "addi a3, a3, 128\n"           // next B row: 32 * 4 bytes
      "addi a4, a4, -32\n"
      "bnez a4, k_loop_32\n"

      // Store row i
      "vse32.v v8,  (t2)\n"

      // Store row i+1
      "addi a5, t2, 128\n"
      "vse32.v v9,  (a5)\n"

      // Store row i+2
      "addi a5, t2, 256\n"
      "vse32.v v10, (a5)\n"

      // Store row i+3
      "addi a5, t2, 384\n"
      "vse32.v v11, (a5)\n"

      // Advance to next 4-row block
      "addi t1, t1, 512\n"           // 4 * 32 * 4 bytes
      "addi t2, t2, 512\n"
      "addi t0, t0, -1\n"
      "bnez t0, row_block_loop_32\n"

      "ret\n"
  );
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_64x64x64_4row(const float *A, const float *B, float *C) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      // A: a0, B: a1, C: a2
      // row-major, FP32
      // M = N = K = 64
      // 4-row blocking:
      //   row i   accumulators: v8,  v9
      //   row i+1 accumulators: v10, v11
      //   row i+2 accumulators: v12, v13
      //   row i+3 accumulators: v14, v15

      // FP32 on VLEN=1024 -> VLMAX = 32
      "li a3, 32\n"
      "vsetvli zero, a3, e32, m1, ta, ma\n"

      // row-block count = 64 / 4 = 16
      "li t0, 16\n"
      "mv t1, a0\n"                  // t1 = A row-block base (row i)
      "mv t2, a2\n"                  // t2 = C row-block base (row i)

      "row_block_loop:\n"
      // zero accumulators for 4 rows x 2 column chunks
      "vmv.v.i v8,  0\n"
      "vmv.v.i v9,  0\n"

      "vmv.v.i v10, 0\n"
      "vmv.v.i v11, 0\n"

      "vmv.v.i v12, 0\n"
      "vmv.v.i v13, 0\n"

      "vmv.v.i v14, 0\n"
      "vmv.v.i v15, 0\n"

      // A row pointers for rows i, i+1, i+2, i+3
      "mv t3, t1\n"                  // t3 = A[i][0]
      "addi t4, t1, 256\n"           // t4 = A[i+1][0], 64*4 = 256B
      "addi t5, t1, 512\n"           // t5 = A[i+2][0]
      "addi t6, t1, 768\n"           // t6 = A[i+3][0]

      // B row pointer and K counter
      "mv a3, a1\n"                  // a3 = B[0][0]
      "li a4, 2048\n"                  // a4 = k counter

      "k_loop:\n"
      // load 4 scalars: A[i+r][k], r = 0..3
      "flw fa0, 0(t3)\n"
      "flw fa1, 0(t4)\n"
      "flw fa2, 0(t5)\n"
      "flw fa3, 0(t6)\n"

      "vsetvli zero, a4, e32, m1, ta, ma\n"
      // load one full row of B[k][:] as 2 vector chunks
      "vle32.v v0, (a3)\n"           // B[k][ 0:31 ]
      "addi a5, a3, 128\n"
      "vle32.v v1, (a5)\n"           // B[k][32:63 ]

      // Row i
      "vfmacc.vf v8,  fa0, v0\n"
      "vfmacc.vf v9,  fa0, v1\n"

      // Row i+1
      "vfmacc.vf v10, fa1, v0\n"
      "vfmacc.vf v11, fa1, v1\n"

      // Row i+2
      "vfmacc.vf v12, fa2, v0\n"
      "vfmacc.vf v13, fa2, v1\n"

      // Row i+3
      "vfmacc.vf v14, fa3, v0\n"
      "vfmacc.vf v15, fa3, v1\n"

      // Advance A row pointers and B row pointer
      "addi t3, t3, 4\n"
      "addi t4, t4, 4\n"
      "addi t5, t5, 4\n"
      "addi t6, t6, 4\n"
      "addi a3, a3, 256\n"           // next B row: 64 * 4 bytes
      "addi a4, a4, -32\n"
      "bnez a4, k_loop\n"

      // Store row i
      "vse32.v v8,  (t2)\n"
      "addi a5, t2, 128\n"
      "vse32.v v9,  (a5)\n"

      // Store row i+1
      "addi a3, t2, 256\n"
      "vse32.v v10, (a3)\n"
      "addi a5, a3, 128\n"
      "vse32.v v11, (a5)\n"

      // Store row i+2
      "addi a3, t2, 512\n"
      "vse32.v v12, (a3)\n"
      "addi a5, a3, 128\n"
      "vse32.v v13, (a5)\n"

      // Store row i+3
      "addi a3, t2, 768\n"
      "vse32.v v14, (a3)\n"
      "addi a5, a3, 128\n"
      "vse32.v v15, (a5)\n"

      // Advance to next 4-row block
      "addi t1, t1, 1024\n"          // 4 * 64 * 4 bytes
      "addi t2, t2, 1024\n"
      "addi t0, t0, -1\n"
      "bnez t0, row_block_loop\n"

      "ret\n"
  );
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_128x128x128_4row(const float *A, const float *B, float *C) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      "li a3, 32\n"
      "vsetvli zero, a3, e32, m1, ta, ma\n"

      // 128 / 4 = 32 row blocks
      "li t0, 32\n"
      "mv t1, a0\n"
      "mv t2, a2\n"

      "row_block_loop_128:\n"
      // 4 rows × 4 chunks
      "vmv.v.i v8,  0\n"   "vmv.v.i v9,  0\n"
      "vmv.v.i v10, 0\n"   "vmv.v.i v11, 0\n"

      "vmv.v.i v12, 0\n"   "vmv.v.i v13, 0\n"
      "vmv.v.i v14, 0\n"   "vmv.v.i v15, 0\n"

      "vmv.v.i v16, 0\n"   "vmv.v.i v17, 0\n"
      "vmv.v.i v18, 0\n"   "vmv.v.i v19, 0\n"

      "vmv.v.i v20, 0\n"   "vmv.v.i v21, 0\n"
      "vmv.v.i v22, 0\n"   "vmv.v.i v23, 0\n"

      "mv t3, t1\n"
      "addi t4, t1, 512\n"
      "addi t5, t1, 1024\n"
      "addi t6, t1, 1536\n"

      "mv a3, a1\n"
      "li a4, 4096\n"

      "k_loop_128:\n"
      "flw fa0, 0(t3)\n"
      "flw fa1, 0(t4)\n"
      "flw fa2, 0(t5)\n"
      "flw fa3, 0(t6)\n"

      "vsetvli zero, a4, e32, m1, ta, ma\n"
      "vle32.v v0, (a3)\n"
      "addi a5, a3, 128\n"
      "vle32.v v1, (a5)\n"
      "addi a5, a3, 256\n"
      "vle32.v v2, (a5)\n"
      "addi a5, a3, 384\n"
      "vle32.v v3, (a5)\n"

      // row i
      "vfmacc.vf v8,  fa0, v0\n"
      "vfmacc.vf v9,  fa0, v1\n"
      "vfmacc.vf v10, fa0, v2\n"
      "vfmacc.vf v11, fa0, v3\n"

      // row i+1
      "vfmacc.vf v12, fa1, v0\n"
      "vfmacc.vf v13, fa1, v1\n"
      "vfmacc.vf v14, fa1, v2\n"
      "vfmacc.vf v15, fa1, v3\n"

      // row i+2
      "vfmacc.vf v16, fa2, v0\n"
      "vfmacc.vf v17, fa2, v1\n"
      "vfmacc.vf v18, fa2, v2\n"
      "vfmacc.vf v19, fa2, v3\n"

      // row i+3
      "vfmacc.vf v20, fa3, v0\n"
      "vfmacc.vf v21, fa3, v1\n"
      "vfmacc.vf v22, fa3, v2\n"
      "vfmacc.vf v23, fa3, v3\n"

      "addi t3, t3, 4\n"
      "addi t4, t4, 4\n"
      "addi t5, t5, 4\n"
      "addi t6, t6, 4\n"
      "addi a3, a3, 512\n"
      "addi a4, a4, -32\n"
      "bnez a4, k_loop_128\n"

      // store row i
      "vse32.v v8, (t2)\n"
      "addi a5, t2, 128\n"
      "vse32.v v9, (a5)\n"
      "addi a5, t2, 256\n"
      "vse32.v v10, (a5)\n"
      "addi a5, t2, 384\n"
      "vse32.v v11, (a5)\n"

      // row i+1
      "addi a3, t2, 512\n"
      "vse32.v v12, (a3)\n"
      "addi a5, a3, 128\n"
      "vse32.v v13, (a5)\n"
      "addi a5, a3, 256\n"
      "vse32.v v14, (a5)\n"
      "addi a5, a3, 384\n"
      "vse32.v v15, (a5)\n"

      // row i+2
      "addi a3, t2, 1024\n"
      "vse32.v v16, (a3)\n"
      "addi a5, a3, 128\n"
      "vse32.v v17, (a5)\n"
      "addi a5, a3, 256\n"
      "vse32.v v18, (a5)\n"
      "addi a5, a3, 384\n"
      "vse32.v v19, (a5)\n"

      // row i+3
      "addi a3, t2, 1536\n"
      "vse32.v v20, (a3)\n"
      "addi a5, a3, 128\n"
      "vse32.v v21, (a5)\n"
      "addi a5, a3, 256\n"
      "vse32.v v22, (a5)\n"
      "addi a5, a3, 384\n"
      "vse32.v v23, (a5)\n"

      "addi t1, t1, 1024\n"
      "addi t1, t1, 1024\n"
      "addi t2, t2, 1024\n"
      "addi t2, t2, 1024\n"
      "addi t0, t0, -1\n"
      "bnez t0, row_block_loop_128\n"
      "ret\n");
}
