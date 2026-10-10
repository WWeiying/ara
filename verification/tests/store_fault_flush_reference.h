#ifndef STORE_FAULT_FLUSH_REFERENCE_H
#define STORE_FAULT_FLUSH_REFERENCE_H
#include <stdint.h>
#define SFF_GUARD UINT64_C(0xd6a52c7193e80fb4)
#define SFF_BAD UINT64_C(0xe0000000)
#define SFF_CHECKS 134
static const uint16_t sff_offsets[8] = {0, 6, 16, 24, 32, 40, 48, 56};
static uint64_t sff_word(unsigned source, unsigned index) {
  if (index < 2 || index >= 18) return SFF_GUARD;
  return (source ? UINT64_C(0x7928d60be14c953a) : UINT64_C(0x136fe802a5974cdb)) ^
         (UINT64_C(0x01030507090b0d0f) * (index - 2));
}
static uint64_t sff_expected(unsigned buffer, unsigned index) {
  if (buffer == 2) return index >= 2 && index < 10 ? sff_word(1, index) : SFF_GUARD;
  return sff_word(buffer == 1 || buffer == 4, index);
}
#endif
