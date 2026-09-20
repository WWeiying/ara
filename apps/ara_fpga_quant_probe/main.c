/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>
#include <string.h>
#ifdef SPIKE
extern void printstr(const char *);
#define REPORT(s) printstr(s)
#else
#include "printf.h"
#define REPORT(s) printf(s)
#endif
#include "../llama_q4km_micro/micro_kernels.c"

static float input[QK_K] __attribute__((aligned(128)));
static uint8_t scratch[QK_K] __attribute__((aligned(128)));
static uint64_t trace[18] __attribute__((aligned(128)));
static block_q8_K output __attribute__((aligned(128)));

extern int probe_quant_ops(const float *, uint8_t *, uint64_t *);

int main(void) {
  REPORT("QUANT_PROBE v2 begin\n");
  for (unsigned i = 0; i < QK_K; ++i)
    input[i] = (float)(i % 31u) - 15.0f;

  int rc = probe_quant_ops(input, scratch, trace);
#ifndef SPIKE
  for (unsigned i = 1; i <= 16; ++i)
    printf("QUANT_VALUE %u %x\n", i, (unsigned)trace[i]);
#endif
  if (rc) {
#ifndef SPIKE
    printf("QUANT_PROBE FAIL operation=%lu\n", (unsigned long)trace[0]);
#else
    REPORT("QUANT_PROBE FAIL operations\n");
#endif
    return 1;
  }

  REPORT("QUANT_PROBE original_begin\n");
  q4km_quantize_row_q8_K(input, &output, QK_K);
  uint32_t bits;
  memcpy(&bits, &output.d, sizeof(bits));
  unsigned errors = bits != 0x3df1e3c8u;
  for (unsigned b = 0; b < QK_K / 16; ++b) {
    int sum = 0;
    for (unsigned j = 0; j < 16; ++j) {
      unsigned i = b * 16 + j;
      int n = ((int)(i % 31) - 15) * 127;
      int q = n < 0 ? -((-n + 7) / 15) : (n + 7) / 15;
      errors += output.qs[i] != q;
      sum += q;
    }
    errors += output.bsums[b] != sum;
  }
#ifndef SPIKE
  printf("QUANT_PROBE original_done errors=%u d_bits=%x\n", errors, bits);
#endif
  if (errors) return 2;
  REPORT("QUANT_PROBE PASS\n");
  return 0;
}
