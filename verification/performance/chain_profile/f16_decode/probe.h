#ifndef CHAIN_F16_PROBE_H
#define CHAIN_F16_PROBE_H
#include <stdint.h>

enum { F16_SPANS = 13, F16_TRIALS = 4 };
typedef struct { uint64_t before, after; } f16_span_t;
typedef struct __attribute__((aligned(64))) {
  unsigned char before[64];
  f16_span_t spans[F16_SPANS];
  unsigned char after[64];
} f16_probe_buffer_t;
extern volatile f16_probe_buffer_t f16_probe_buffer;
#define f16_spans f16_probe_buffer.spans

/* Integer stores only. These are issue-side boundaries, not vector drains. */
#define F16_STAMP(index, member) do { \
  uintptr_t stamp; \
  volatile uint64_t *where = &f16_spans[(index)].member; \
  __asm__ volatile("rdcycle %0\nsd %0, 0(%1)" \
                   : "=&r"(stamp) : "r"(where) : "memory"); \
} while (0)
#define F16_BEGIN(index) F16_STAMP(index, before)
#define F16_END(index) F16_STAMP(index, after)
#endif
