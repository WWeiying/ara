#include "printf.h"
#include <stdint.h>

extern const float quant_query0_f32[];
extern void quantize_row_q8_0(const float *, void *, int64_t);
static unsigned char query[136] __attribute__((aligned(64)));

int main(void) {
  quantize_row_q8_0(quant_query0_f32, query, 128);
  unsigned hash = 2166136261u;
  for (unsigned i = 0; i < sizeof(query); ++i) hash = (hash ^ query[i])*16777619u;
#if PROBE_SAFE_DRAIN
  /* No undefined vector-tail value enters a live scalar argument register. */
  __asm__ volatile("vmv.x.s zero,v8\nfence rw,rw" : : : "memory");
#else
  /* Reproduce the actual batch-main allocation at 0x800005d0, not a new
   * hardware operation: printf's variadic prologue subsequently saves a4. */
  register uintptr_t dead __asm__("a4");
  __asm__ volatile("vmv.x.s %0,v12\nfence rw,rw" : "=r"(dead) : : "memory");
  (void)dead;
#endif
  printf("QUANT_DRAIN_PROBE safe=%u hash=%08x\n", PROBE_SAFE_DRAIN, hash);
  return 0;
}
