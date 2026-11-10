#include "akv/akv_features.h"
#include <math.h>
#include <stdint.h>

typedef struct { unsigned function, input; } libm_request_t;
typedef struct {
  unsigned dot, scale, mask, head, index;
  akv_attention_features_t features;
} transform_request_t;
#include "requests.h"
volatile uint32_t probe_results[REQUEST_COUNT + DIRECTED_COUNT][2];

static float from_bits(uint32_t bits) {
  union { uint32_t bits; float value; } u = {.bits=bits};
  return u.value;
}

int probe_main(void) {
  float (*volatile functions[2])(float) = {expf,tanhf};
  for (unsigned i=0; i<REQUEST_COUNT+DIRECTED_COUNT; ++i) {
    uintptr_t saved, flags, restored;
    __asm__ volatile("frcsr %0\ncsrwi fcsr,0" : "=r"(saved) : : "memory");
    union { uint32_t bits; float value; } u;
    if (i < REQUEST_COUNT) {
      u.value = functions[requests[i].function](from_bits(requests[i].input));
    } else {
      const transform_request_t *r = &directed_requests[i-REQUEST_COUNT];
      u.value = akv_attention_score_transform(from_bits(r->dot),from_bits(r->scale),
          r->mask,r->head,r->index,&r->features);
    }
    __asm__ volatile("frcsr %0\ncsrw fcsr,%1" : "=&r"(flags) : "r"(saved) : "memory");
    __asm__ volatile("frcsr %0" : "=r"(restored) : : "memory");
    if (restored != saved) return 1;
    probe_results[i][0] = u.bits;
    probe_results[i][1] = flags;
  }
  return 0;
}
