#include <stddef.h>
#include <stdint.h>

int boundary_body(void) __attribute__((noinline));
#define main boundary_body
#include "native_runtime_main.c"
#undef main
#include "expected.h"

/* Volatile byte reads cover even capture tails unused by the four problems. */
static uint64_t boundary_fnv(const void *data, size_t bytes) {
  const volatile unsigned char *p = data;
  uint64_t value = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < bytes; ++i)
    value = (value ^ p[i]) * UINT64_C(1099511628211);
  return value;
}

static unsigned boundary_payload(const char *name, const void *data,
                                 size_t bytes, uint64_t expected) {
  const uint64_t actual = boundary_fnv(data, bytes);
  const unsigned errors = actual != expected;
  printf("AKV_BOUNDARY_PAYLOAD name=%s bytes=%lu fnv=%016lx expected=%016lx errors=%u\n",
         name, (unsigned long)bytes, (unsigned long)actual,
         (unsigned long)expected, errors);
  return errors;
}

int main(void) {
  const int body = boundary_body();
  unsigned errors = body != 0;
  errors += boundary_payload("q", candidate_query_f32, 6144, BOUNDARY_EXPECT_Q);
  errors += boundary_payload("k", candidate_key, 131072, BOUNDARY_EXPECT_K);
  errors += boundary_payload("v", candidate_value, 131072, BOUNDARY_EXPECT_V);
  printf("AKV_BOUNDARY_DONE body=%d checks=3 errors=%u\n", body, errors);
  return errors != 0;
}
