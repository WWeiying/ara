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
void rvv_random(uint32_t *src0, uint32_t *src1);

// Function prototype using vector extension

int main() {

    rvv_random(src1,src2);

    return 0;
}

#include <stdint.h>

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void rvv_random(uint32_t *src0, uint32_t *src1) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      // a0 = src0
      // a1 = src1

      ".include \"test/rvv_random.S\"\n"

      "ret\n");
}
