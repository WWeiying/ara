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

#define TOTAL_ELEMENTS 4096
#define TEST_ELEMENTS  512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Function prototype using vector extension
void gemv_f32_32x64(const float *matrix, const float *vector, float *dest);
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest);
void gemv_f32_32x256(const float *matrix, const float *vector, float *dest);

int main() {
    const float a = 6.66;

    gemv_f32_32x128(src1,src2,src1);

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x64(const float *matrix, const float *vector, float *dest) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      // Fixed-shape kernel: M=32, N=64, FP32
      // FP32 on VLEN=1024 -> VLMAX = 32
      "li t3, 32\n"
      "vsetvli zero, t3, e32, m1, ta, ma\n"

      // Construct x without vle: build once with vid, then replicate
      "vid.v v0\n"
      "vfcvt.f.x.v v0, v0\n"
      "vmv.v.v v1, v0\n"

      // row pointer
      "mv t0, a0\n"

      // row count = 32
      "li t6, 1024\n"

      "row_loop_32x64:\n"
      "vsetvli zero, t6, e32, m1, ta, ma\n"
      // load one row of matrix as 2 vector chunks
      "vle32.v v4, (t0)\n"
      "addi t2, t0, 128\n"
      "vle32.v v5, (t2)\n"

      // accumulate
      "vmv.v.i v8, 0\n"
      "vfmacc.vv v8, v4, v0\n"
      "vfmacc.vv v8, v5, v1\n"

      // horizontal reduction to scalar
      "vmv.v.i v16, 0\n"
      "vfredsum.vs v16, v8, v16\n"
      "vfmv.f.s fa0, v16\n"
      "fsw fa0, (a2)\n"

      // next row / next output
      "addi t0, t0, 256\n"   // 64 * sizeof(float)
      "addi a2, a2, 4\n"
      "addi t6, t6, -32\n"
      "bnez t6, row_loop_32x64\n"

      "ret\n");
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      // Fixed-shape kernel: M=32, N=128, FP32
      "li t3, 32\n"
      "vsetvli zero, t3, e32, m1, ta, ma\n"

      // Construct x without vle: build once with vid, then replicate with vmv
      "vid.v v0\n"
      "vfcvt.f.x.v v0, v0\n"
      "vmv.v.v v1, v0\n"
      "vmv.v.v v2, v0\n"
      "vmv.v.v v3, v0\n"

      "mv t0, a0\n"       // row pointer
      "li t6, 1024\n"       // row counter
      "row_loop:\n"
      "vsetvli t5, t6, e32, m1, ta, ma\n"
      "vle32.v v4, (t0)\n"
      "addi t2, t0, 128\n"
      "vle32.v v5, (t2)\n"
      "addi t2, t0, 256\n"
      "vle32.v v6, (t2)\n"
      "addi t2, t0, 384\n"
      "vle32.v v7, (t2)\n"
      "vmv.v.i v8, 0\n"
      "vfmacc.vv v8, v4, v0\n"
      "vfmacc.vv v8, v5, v1\n"
      "vfmacc.vv v8, v6, v2\n"
      "vfmacc.vv v8, v7, v3\n"

      // horizontal reduction to scalar
      "vmv.v.i v16, 0\n"
      "vfredsum.vs v16, v8, v16\n"
      "vfmv.f.s fa0, v16\n"
      "fsw fa0, (a2)\n"

      // next row / next output
      "addi t0, t0, 512\n" // 128 * sizeof(float)
      "addi a2, a2, 4\n"
      "sub t6, t6, t5\n"
      "bnez t6, row_loop\n"
      "ret\n");
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x256(const float *matrix, const float *vector, float *dest) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      // Fixed-shape kernel: M=32, N=256, FP32
      // FP32 on VLEN=1024 -> VLMAX = 32
      "li t3, 32\n"
      "vsetvli zero, t3, e32, m1, ta, ma\n"

      // Construct x without vle: build once with vid, then replicate
      "vid.v v0\n"
      "vfcvt.f.x.v v0, v0\n"
      "vmv.v.v v1, v0\n"
      "vmv.v.v v2, v0\n"
      "vmv.v.v v3, v0\n"
      "vmv.v.v v4, v0\n"
      "vmv.v.v v5, v0\n"
      "vmv.v.v v6, v0\n"
      "vmv.v.v v7, v0\n"

      // row pointer
      "mv t0, a0\n"

      // row count = 32
      "li t6, 1024\n"

      "row_loop_32x256:\n"
      "vsetvli zero, t6, e32, m1, ta, ma\n"
      // load one row of matrix as 8 vector chunks
      "vle32.v v8, (t0)\n"
      "addi t2, t0, 128\n"
      "vle32.v v9, (t2)\n"
      "addi t2, t0, 256\n"
      "vle32.v v10, (t2)\n"
      "addi t2, t0, 384\n"
      "vle32.v v11, (t2)\n"
      "addi t2, t0, 512\n"
      "vle32.v v12, (t2)\n"
      "addi t2, t0, 640\n"
      "vle32.v v13, (t2)\n"
      "addi t2, t0, 768\n"
      "vle32.v v14, (t2)\n"
      "addi t2, t0, 896\n"
      "vle32.v v15, (t2)\n"

      // accumulate
      "vmv.v.i v16, 0\n"
      "vfmacc.vv v16, v8,  v0\n"
      "vfmacc.vv v16, v9,  v1\n"
      "vfmacc.vv v16, v10, v2\n"
      "vfmacc.vv v16, v11, v3\n"
      "vfmacc.vv v16, v12, v4\n"
      "vfmacc.vv v16, v13, v5\n"
      "vfmacc.vv v16, v14, v6\n"
      "vfmacc.vv v16, v15, v7\n"

      // horizontal reduction to scalar
      "vmv.v.i v24, 0\n"
      "vfredsum.vs v24, v16, v24\n"
      "vfmv.f.s fa0, v24\n"
      "fsw fa0, (a2)\n"

      // next row / next output
      "addi t0, t0, 1024\n"   // 256 * sizeof(float)
      "addi a2, a2, 4\n"
      "addi t6, t6, -32\n"
      "bnez t6, row_loop_32x256\n"

      "ret\n");
}
