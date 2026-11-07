/* Read-only payload audit after the unchanged two-trial profile body. */
#include <stddef.h>
#include <stdint.h>

#include "integrity_config.h"
#include "printf.h"

extern int q6_profile_body(void);
extern const float profile_input[2048];
extern const unsigned char profile_weights[107520];

static uint64_t fnv1a64(volatile const unsigned char *data, size_t bytes) {
  uint64_t hash = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < bytes; ++i) {
    hash ^= data[i];
    hash *= UINT64_C(1099511628211);
  }
  return hash;
}

static unsigned check_payload(const char *tag,
                              volatile const unsigned char *data,
                              size_t bytes, uint64_t expected) {
  const uint64_t actual = fnv1a64(data, bytes);
  printf("CHAIN_Q6_INPUT_INTEGRITY tag=%s bytes=%u expected=%016lx actual=%016lx\n",
         tag, (unsigned)bytes, (unsigned long)expected, (unsigned long)actual);
  return actual != expected;
}

int main(void) {
  const int body_status = q6_profile_body();
  __asm__ volatile("fence rw, rw" : : : "memory");
  unsigned errors = check_payload(
      "activation", (volatile const unsigned char *)profile_input, 8192,
      Q6_INPUT_EXPECTED_HASH);
  errors += check_payload("weight", profile_weights, 107520,
                          Q6_WEIGHT_EXPECTED_HASH);
  printf("CHAIN_Q6_INPUT_INTEGRITY_DONE errors=%u\n", errors);
  return body_status != 0 || errors != 0;
}
