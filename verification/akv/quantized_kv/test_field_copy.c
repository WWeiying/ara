#define _GNU_SOURCE
#include "software/akv/experimental/quantized_kv/field_copy.h"
#include <assert.h>
#include <fenv.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>

int main(void) {
  unsigned char bytes[16];
  assert(feclearexcept(FE_ALL_EXCEPT) == 0);
  for (unsigned value = 0; value < 65536; ++value) {
    uint16_t expected = (uint16_t)value;
    for (unsigned offset = 0; offset < 8; ++offset) {
      memcpy(bytes + offset, &expected, 2);
      uint16_t actual;
      AKV_QUANT_FIELD_COPY(&actual, bytes + offset, 2);
      assert(actual == expected);
    }
  }
  const uint32_t patterns[] = {0, 0x80000000, 1, 0x007fffff, 0x00800000,
    0x7f7fffff, 0x7f800000, 0xff800000, 0x7f800001, 0x7fc12345, 0xffffffff};
  for (unsigned i = 0; i < sizeof(patterns)/sizeof(patterns[0]); ++i) {
    for (unsigned offset = 0; offset < 8; ++offset) {
      memcpy(bytes + offset, &patterns[i], 4);
      float value;
      uint32_t bits;
      AKV_QUANT_FIELD_COPY(&value, bytes + offset, 4);
      AKV_QUANT_FIELD_COPY(&bits, &value, 4);
      assert(bits == patterns[i]);
    }
  }
  assert(fetestexcept(FE_ALL_EXCEPT) == 0);
  const size_t page = (size_t)sysconf(_SC_PAGESIZE);
  unsigned char *p = mmap(NULL, 2*page, PROT_READ|PROT_WRITE,
                         MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
  assert(p != MAP_FAILED);
  assert(mprotect(p + page, page, PROT_NONE) == 0);
  memset(p + page - 4, 0xff, 4);
  uint16_t h; uint32_t w;
  AKV_QUANT_FIELD_COPY(&h, p + page - 2, 2);
  AKV_QUANT_FIELD_COPY(&w, p + page - 4, 4);
  assert(h == UINT16_MAX && w == UINT32_MAX);
  assert(munmap(p, 2*page) == 0);
  puts("FIELD_COPY_PASS half_patterns=65536 offsets=8 fp_flags=0 guard_page=1");
  return 0;
}
