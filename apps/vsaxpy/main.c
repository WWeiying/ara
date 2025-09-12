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

//enum { TOTAL_ELEMENTS = 1024};
#define TOTAL_ELEMENTS 1024

//extern int16_t source[TOTAL_ELEMENTS] __attribute__((aligned(2), section(".data.source")));
extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));
extern int32_t dest[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.dest")));

//extern const uint32_t _source_size;
extern const uint32_t _src1_size;
extern const uint32_t _src2_size;
extern const uint32_t _dest_size;

// Function prototype using vector extension
void vsaxpy(int n, const float a, const float *src1, float *src2);

int main() {
    //const int VLEN = 256;      // Vector length in bits
    //const int ELEMENT_SIZE = 16; // Size in bits

    
    // Calculate max vector elements per segment
    //const int MAX_VECTOR_ELEMENTS = VLEN / ELEMENT_SIZE;
    
 //   int scalar_multiplier = 3;
    
    // Perform vector operation
    //vec_mul_shift(TOTAL_ELEMENTS, source, dest, scalar_multiplier);
    const float a = 6.66;

    vsaxpy(TOTAL_ELEMENTS, a, src1, src2);

    return 0;
}

#ifdef vec
__attribute__((noinline, used)) void vsaxpy(int n, const float a, const float *src1, float *src2) {
#pragma clang loop vectorize(enable)
    for (int i=0; i<n; i++) {
        src2[i]=a*src1[i]+src2[i];
    }
}
#else
__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void vsaxpy(int n, const float a, const float *src1, float *src2) {
    __asm__ volatile (
    "saxpy:\n"
    "vsetvli a4, a0, e32, m8, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "sub a0, a0, a4\n"
    "slli a4，a4，2\n"
    "add a1, a1, a4\n"
    "vle32.v v8, (a2)\n"
    "vfmacc.vf v8, fa0, v0\n"
    "vse32.v v8, (a2)\n"
    "add a2, a2, a4\n"
    "bnez a0, saxpy\n"
    "ret\n"
    );
}
#endif
