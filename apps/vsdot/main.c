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

//extern int16_t source[TOTAL_ELEMENTS] __attribute__((aligned(2), section(".data.source")));
extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));
extern float dest[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.dest")));

//extern const uint32_t _source_size;
extern const uint32_t _src1_size;
extern const uint32_t _src2_size;
extern const uint32_t _dest_size;

float vsdot(const float *a, const float *b, int avl);

int main() {

  vsdot(src1, src2, TOTAL_ELEMENTS);
//  #ifndef SPIKE
//  perf_time();
//  #endif
  return 0;
}

// Vector processing function
__attribute__((naked, target("arch=rv64gcv")))
float vsdot(const float *a, const float *b, int avl) {
    __asm__ volatile (
  #ifndef SPIKE
        "rdcycle zero\n"
  #endif
        "vsetvli t0, a2, e32, m1, ta, ma\n"
        "vmv.v.i v0, 0\n"
        "dotp_loop:\n"
        "vsetvli t0, a2, e32, m1, ta, ma\n"
        "vle32.v v8, (a0)\n"
        "sub a2, a2, t0\n"
        "vle32.v v16, (a1)\n"
        "slli t1, t0, 2\n"
        "vfmul.vv v24, v8, v16\n"
        "add a0, a0, t1\n"
        "vfredsum.vs v0, v24, v0\n"
        "add a1, a1, t1\n"
        "bnez a2, dotp_loop\n"               
        "vfmv.f.s fa0, v0\n"
        "ret\n"
    );
}

