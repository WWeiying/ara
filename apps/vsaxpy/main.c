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
void vsaxpy(int n, const float a, const float *src1, float *src2);

int main() {
    const float a = 6.66;

    vsaxpy(32, a, src1, src2);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void vsaxpy(int n, const float a, const float *src1, float *src2) {
    __asm__ volatile (
    #ifndef SPIKE
    "rdcycle zero\n"
    #endif
    "saxpy:\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "sub a0, a0, t0\n"
    "vle32.v v8, (a2)\n"
    "add a1, a1, t1\n"
    "vfmacc.vf v8, fa0, v0\n"
    "slli t1, t0, 2\n"
    "vse32.v v8, (a2)\n"
    "add a2, a2, t1\n"
    "bnez a0, saxpy\n"
    "ret\n"
    );
}
//#ifdef vec
//__attribute__((noinline, used)) void vsaxpy(int n, const float a, const float *src1, float *src2) {
//    for (int i=0; i<n; i++) {
//        src2[i]=a*src1[i]+src2[i];
//    }
//}
//#else
//#endif
