#include <riscv_vector.h>
#include <stddef.h>
#include <stdint.h>

#include "printf.h"

#define ARENA_BYTES (4u * 1024u * 1024u)
#define WORDS_PER_PROBE 32u

static uint32_t arena[ARENA_BYTES / sizeof(uint32_t)]
    __attribute__((aligned(128)));

static int probe(size_t byte_offset, uint32_t seed) {
  uint32_t *address = &arena[byte_offset / sizeof(uint32_t)];
  const size_t vl = __riscv_vsetvl_e32m1(WORDS_PER_PROBE);
  const vuint32m1_t indices = __riscv_vid_v_u32m1(vl);
  const vuint32m1_t values = __riscv_vadd_vx_u32m1(indices, seed, vl);

  __riscv_vse32_v_u32m1(address, values, vl);
  asm volatile("fence rw, rw" ::: "memory");
  const vuint32m1_t loaded = __riscv_vle32_v_u32m1(address, vl);
  static uint32_t observed[WORDS_PER_PROBE] __attribute__((aligned(128)));
  __riscv_vse32_v_u32m1(observed, loaded, vl);
  asm volatile("fence rw, rw" ::: "memory");

  for (size_t i = 0; i < WORDS_PER_PROBE; ++i) {
    if (observed[i] != seed + i) {
      printf("L2 probe FAIL offset=0x%x index=%d expected=0x%x actual=0x%x\n",
             (uint32_t)byte_offset, (int)i, seed + (uint32_t)i,
             observed[i]);
      return 1;
    }
  }
  return 0;
}

int main(void) {
  static const size_t offsets[] = {
      0,
      (1u << 20) - 128,
      (1u << 20) + 128,
      (2u << 20) + 128,
      ARENA_BYTES - 128,
  };
  int failures = 0;

  for (size_t i = 0; i < sizeof(offsets) / sizeof(offsets[0]); ++i) {
    failures += probe(offsets[i], 0x13570000u + (uint32_t)(i << 8));
  }

  printf("Simulation-only L2 4 MiB boundary smoke: %s\n",
         failures == 0 ? "PASS" : "FAIL");
  return failures;
}
