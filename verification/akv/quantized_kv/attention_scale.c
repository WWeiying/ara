#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Exact expression in the pinned Qwen2 graph; not rounded capture JSON. */
int main(void) {
  volatile float dim = 128.0f;
  const float scale = 1.0f / sqrtf(dim);
  uint32_t bits;
  memcpy(&bits, &scale, sizeof(bits));
  printf("%08x\n", bits);
  return 0;
}
